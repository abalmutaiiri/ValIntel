"""Main application window: composes independent widgets and services."""
from __future__ import annotations
import copy
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import keyring
from PySide6.QtCore import QObject, QRectF, Qt, QSettings, QTimer, Signal, QUrl
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar, QFileDialog,
    QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)
from ..config import REFRESH_SECONDS, KNOWN_AGENTS
from ..models.player import Player
from ..models.snapshot import Snapshot
from ..services.riot_api import RiotAPI
from ..services.agent_lock_service import AgentLockService
from ..services.agent_assets import fetch_agent_icon
from ..analysis.match_estimator import estimate_match
from ..analysis.pattern_checker import PatternReport, demo_reports, scan_players
from ..analysis.name_history import (
    NameObservation, normalize_observation, read_observations, write_observations,
    consolidate, changes, by_act, example_observations,
)
from ..demo import demo_snapshot
from .theme import APP_TITLE, PALETTE, ROLE, STYLESHEET
from .credentials import CREDENTIAL_SERVICE, CREDENTIAL_USERNAME, get_key
from .widgets import label, button, panel, separator
from .bridge import Bridge
from .gauge import Gauge
from .agent_tile import AgentTile
from .player_row import PlayerRow
from .settings_dialog import SettingsDialog

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ValIntel  ·  Tactical Companion")
        self.setMinimumSize(1080, 760)
        self.resize(1510, 970)
        self.setStyleSheet(STYLESHEET)

        self.settings_store = QSettings("ValIntel", "Desktop")
        self.auto_refresh = self.settings_store.value("auto_refresh", True, type=bool)
        self.stats_on = self.settings_store.value("stats_enabled", False, type=bool)
        self.key = get_key() or os.environ.get("HENRIK_API_KEY", "")
        self.demo = False
        self.current = Snapshot(status="Ready to connect. Start VALORANT or try Demo Mode.")
        self.api = RiotAPI()
        self.lock_api = AgentLockService()
        self.catalog_api = RiotAPI()
        self.bridge = Bridge()
        self.bridge.event.connect(self.on_event)
        self.bridge.portrait.connect(self.on_portrait)
        self.bridge.catalog.connect(self.on_catalog)
        self.icon_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ValIntelIcons")
        self.icon_pixmaps: dict[str, QPixmap] = {}
        self.icon_pending: set[str] = set()
        self.icon_failed: set[str] = set()
        self.live_icon_rows: dict[str, list[PlayerRow]] = {}
        self.agent_items = {name: (agent_id, f"https://media.valorant-api.com/agents/{agent_id}/displayicon.png")
                            for agent_id, name in KNOWN_AGENTS.items()}
        self.agent_tiles: dict[str, AgentTile] = {}
        self.agent_urls: dict[str, str] = {}
        self.selected_name = ""
        self.selected_id = ""
        self.selected_url = ""
        self.action_busy = False
        self.refresh_busy = False
        self.refresh_token = 0
        self.last_refresh = time.monotonic()
        self.lock_deadline: float | None = None
        self.pending_agent: tuple[str, str] | None = None
        self.attempted_stats: set[str] = set()
        self.next_force_stats = False
        self.after_refresh = False
        self.pending_refresh = False
        self.pattern_running = False
        self.pattern_token = 0
        self.pattern_match_id = ""
        self.pattern_results: list[PatternReport] = []
        self.pattern_checkboxes: dict[str, QCheckBox] = {}
        self.pattern_selection: set[str] = set()
        self.history_records: list[NameObservation] = []
        self.closed = False
        self.last_message = "Click an agent portrait to select it in VALORANT."
        self._construct_ui()
        self.populate_agent_tiles()
        self.render_snapshot(self.current)
        self._load_agent_catalog_async()
        self.clock = QTimer(self)
        self.clock.timeout.connect(self.tick)
        self.clock.start(80)
        QTimer.singleShot(600, self.refresh)

    def _construct_ui(self):
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setSpacing(0)
        h.setContentsMargins(0, 0, 0, 0)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(210)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 26, 18, 20)
        side.setSpacing(7)
        brand = QHBoxLayout()
        mark = QLabel("V")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(44, 44)
        mark.setStyleSheet("background: #FF4655; border-radius: 10px; color: white; font-size: 27px; font-weight: 900;")
        brand.addWidget(mark)
        heading = QVBoxLayout()
        heading.setSpacing(0)
        logo = label("VALINTEL")
        logo.setStyleSheet("font-weight: 900; font-size: 15px; letter-spacing: 1px;")
        heading.addWidget(logo)
        heading.addWidget(label("COMPANION", "Hint"))
        brand.addLayout(heading)
        side.addLayout(brand)
        side.addSpacing(30)
        side.addWidget(label("WORKSPACE", "Kicker"))
        self.nav_overview = button("◉   OVERVIEW", lambda: self.scroll_to(self.hero), "NavActive", 45)
        self.nav_agents = button("▦   AGENT SELECT", lambda: self.scroll_to(self.agent_panel), "Nav", 45)
        self.nav_teams = button("♟   LIVE ROSTER", lambda: self.scroll_to(self.roster_panel), "Nav", 45)
        self.nav_insights = button("◈   MATCH INSIGHTS", lambda: self.scroll_to(self.analysis_panel), "Nav", 45)
        self.nav_patterns = button("◎   PATTERN CHECK", lambda: self.scroll_to(self.pattern_panel), "Nav", 45)
        self.nav_history = button("◷   NAME HISTORY", lambda: self.scroll_to(self.history_panel), "Nav", 45)
        self.nav_settings = button("⚙   SETTINGS", self.open_settings, "Nav", 45)
        for nav in (self.nav_overview, self.nav_agents, self.nav_teams, self.nav_insights, self.nav_patterns, self.nav_history, self.nav_settings):
            side.addWidget(nav)
        side.addStretch()
        side.addWidget(separator())
        side.addSpacing(10)
        self.side_connection = label("●  DISCONNECTED")
        self.side_connection.setStyleSheet("color: #F6BE7C; font-weight: 800; font-size: 11px;")
        side.addWidget(self.side_connection)
        side.addWidget(label("Build 2.0  •  PySide6", "Hint"))
        h.addWidget(sidebar)

        self.main_scroll = QScrollArea()
        self.main_scroll.setObjectName("MainScroll")
        self.main_scroll.setWidgetResizable(True)
        self.main_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.main_scroll.setFrameShape(QFrame.Shape.NoFrame)
        main = QWidget()
        main.setObjectName("MainCanvas")
        main.setMinimumWidth(840)
        self.main_scroll.setWidget(main)
        h.addWidget(self.main_scroll, 1)
        layout = QVBoxLayout(main)
        layout.setSpacing(18)
        layout.setContentsMargins(26, 24, 27, 25)

        topbar = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(3)
        titles.addWidget(label("TACTICAL WORKSPACE  /  LIVE COMPANION", "Kicker"))
        titles.addWidget(label("Command center", "PageTitle"))
        topbar.addLayout(titles)
        topbar.addStretch()
        self.mode_pill = label("●  WAITING", "AlertPill")
        self.mode_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        topbar.addWidget(self.mode_pill)
        self.demo_button = button("DEMO MODE", self.toggle_demo)
        topbar.addWidget(self.demo_button)
        topbar.addWidget(button("↻  REFRESH", lambda: self.refresh(), "Primary"))
        layout.addLayout(topbar)

        self.hero = QFrame()
        self.hero.setObjectName("HeaderCard")
        hero_l = QHBoxLayout(self.hero)
        hero_l.setContentsMargins(23, 18, 23, 19)
        hero_l.setSpacing(18)
        hero_txt = QVBoxLayout()
        hero_txt.setSpacing(8)
        hero_txt.addWidget(label("EVERY MATCH. ONE COMMAND CENTER.", "Kicker"))
        hero_txt.addWidget(label("Play with clarity.", "HeroTitle"))
        self.map_label = label("Awaiting VALORANT client connection", "Muted")
        hero_txt.addWidget(self.map_label)
        hero_l.addLayout(hero_txt, 1)
        splash = QLabel("VI")
        splash.setAlignment(Qt.AlignmentFlag.AlignCenter)
        splash.setFixedSize(100, 90)
        splash.setStyleSheet("font-size: 49px; font-weight: 900; color: #FF6571; border: 1px solid #4B3B4A; border-radius: 15px; background: #2B2638;")
        hero_l.addWidget(splash)
        layout.addWidget(self.hero)

        columns = QHBoxLayout()
        columns.setSpacing(16)
        layout.addLayout(columns)
        left_holder = QWidget()
        left = QVBoxLayout(left_holder)
        left.setSpacing(16)
        left.setContentsMargins(0, 0, 0, 0)
        columns.addWidget(left_holder, 3)
        right_holder = QWidget()
        right = QVBoxLayout(right_holder)
        right.setSpacing(16)
        right.setContentsMargins(0, 0, 0, 0)
        columns.addWidget(right_holder, 2)

        # Agent selector
        self.agent_panel, agents_l = panel()
        left.addWidget(self.agent_panel)
        agent_head = QHBoxLayout()
        head_titles = QVBoxLayout()
        head_titles.setSpacing(4)
        head_titles.addWidget(label("AGENT CONTROL", "Kicker"))
        head_titles.addWidget(label("Choose your agent", "SectionTitle"))
        agent_head.addLayout(head_titles)
        agent_head.addStretch()
        self.agent_count = label("29 AGENTS", "Hint")
        agent_head.addWidget(self.agent_count)
        agents_l.addLayout(agent_head)
        filter_l = QHBoxLayout()
        filter_l.setSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search an agent…")
        self.search.textChanged.connect(self.filter_agents)
        filter_l.addWidget(self.search, 1)
        self.role_filter = QComboBox()
        self.role_filter.addItems(["ALL ROLES", "DUELIST", "INITIATOR", "CONTROLLER", "SENTINEL"])
        self.role_filter.setFixedWidth(150)
        self.role_filter.currentTextChanged.connect(self.filter_agents)
        filter_l.addWidget(self.role_filter)
        agents_l.addLayout(filter_l)
        self.agent_grid_scroll = QScrollArea()
        self.agent_grid_scroll.setWidgetResizable(True)
        self.agent_grid_scroll.setFixedHeight(435)
        self.agent_grid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.grid_host = QWidget()
        self.grid_layout = QGridLayout(self.grid_host)
        self.grid_layout.setContentsMargins(2, 3, 2, 3)
        self.grid_layout.setHorizontalSpacing(8)
        self.grid_layout.setVerticalSpacing(9)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.agent_grid_scroll.setWidget(self.grid_host)
        agents_l.addWidget(self.agent_grid_scroll)
        bottom = QHBoxLayout()
        bottom.addWidget(label("CLICK A PORTRAIT TO SELECT", "Hint"))
        bottom.addStretch()
        bottom.addWidget(button("RETRY ICONS", self.retry_icons))
        agents_l.addLayout(bottom)

        # Roster
        self.roster_panel, roster_l = panel()
        left.addWidget(self.roster_panel)
        roster_head = QHBoxLayout()
        rt = QVBoxLayout()
        rt.setSpacing(3)
        rt.addWidget(label("LIVE ROSTER", "Kicker"))
        rt.addWidget(label("Players in your lobby", "SectionTitle"))
        roster_head.addLayout(rt)
        roster_head.addStretch()
        self.count_label = label("0 PLAYERS", "Hint")
        roster_head.addWidget(self.count_label)
        roster_l.addLayout(roster_head)
        roster_l.addWidget(separator())
        self.ally_title = label("●  YOUR TEAM  /  0 PLAYERS")
        self.ally_title.setStyleSheet("color: #72E4AC; font-size: 11px; font-weight: 800; letter-spacing: 1px;")
        roster_l.addWidget(self.ally_title)
        self.allies_box = QVBoxLayout()
        self.allies_box.setSpacing(7)
        roster_l.addLayout(self.allies_box)
        roster_l.addSpacing(8)
        self.enemy_title = label("●  OPPONENTS  /  0 PLAYERS")
        self.enemy_title.setStyleSheet("color: #FF6976; font-size: 11px; font-weight: 800; letter-spacing: 1px;")
        roster_l.addWidget(self.enemy_title)
        self.enemies_box = QVBoxLayout()
        self.enemies_box.setSpacing(7)
        roster_l.addLayout(self.enemies_box)

        # Selected agent card / action controls
        self.command_panel, command_l = panel("Feature")
        right.addWidget(self.command_panel)
        command_l.addWidget(label("AGENT COMMAND", "Kicker"))
        selected = QHBoxLayout()
        selected.setSpacing(16)
        self.selected_portrait = QLabel("?")
        self.selected_portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.selected_portrait.setFixedSize(96, 103)
        self.selected_portrait.setStyleSheet("background: #233245; border: 1px solid #43586A; border-radius: 12px; color: #9DC0D1; font-size: 40px; font-weight: 800;")
        selected.addWidget(self.selected_portrait)
        detail = QVBoxLayout()
        detail.addStretch()
        self.selected_agent_name = label("No agent selected", "BigName")
        detail.addWidget(self.selected_agent_name)
        self.selected_role = label("SELECT FROM THE GRID", "Hint")
        detail.addWidget(self.selected_role)
        detail.addStretch()
        selected.addLayout(detail, 1)
        command_l.addLayout(selected)
        command_l.addWidget(separator())
        self.lock_button = button("LOCK NOW  ·  3 SEC", self.handle_lock_button, "Primary", 47)
        command_l.addWidget(self.lock_button)
        self.lock_progress = QProgressBar()
        self.lock_progress.setRange(0, 100)
        self.lock_progress.setTextVisible(False)
        self.lock_progress.setValue(0)
        command_l.addWidget(self.lock_progress)
        self.agent_feedback = label("Click an agent portrait to select it in VALORANT.", "Muted", True)
        self.agent_feedback.setMinimumHeight(45)
        command_l.addWidget(self.agent_feedback)
        self.command_hint = label("3-second countdown begins only after you press LOCK NOW. Press again to cancel.", "Hint", True)
        command_l.addWidget(self.command_hint)

        # Prediction
        self.analysis_panel, analysis_l = panel()
        right.addWidget(self.analysis_panel)
        at = QHBoxLayout()
        aheading = QVBoxLayout()
        aheading.setSpacing(3)
        aheading.addWidget(label("MATCH INTELLIGENCE", "Kicker"))
        aheading.addWidget(label("Outcome analysis", "SectionTitle"))
        at.addLayout(aheading)
        at.addStretch()
        self.analysis_tag = label("EXPERIMENTAL", "AlertPill")
        at.addWidget(self.analysis_tag)
        analysis_l.addLayout(at)
        self.gauge = Gauge()
        analysis_l.addWidget(self.gauge, 0, Qt.AlignmentFlag.AlignCenter)
        self.coverage = label("STATS COVERAGE   0/0  ·  0/0", "Hint")
        self.coverage.setAlignment(Qt.AlignmentFlag.AlignCenter)
        analysis_l.addWidget(self.coverage)
        self.analysis_message = label("Start a team-based match to compare recent player statistics.", "Muted", True)
        self.analysis_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.analysis_message.setMinimumHeight(48)
        analysis_l.addWidget(self.analysis_message)
        self.insight_label = label("Insights will appear here when both teams have sufficient statistics.", "Hint", True)
        analysis_l.addWidget(self.insight_label)
        self.analyze_btn = button("◈  RUN MATCH ANALYSIS", self.analyze_match, "Teal", 43)
        analysis_l.addWidget(self.analyze_btn)
        analysis_l.addWidget(label("Based on recent K/D and win rates. This is a heuristic, NOT a trained or calibrated AI model.", "Hint", True))

        # Diagnostic panel
        self.activity_panel, activity_l = panel()
        right.addWidget(self.activity_panel)
        activity_l.addWidget(label("CONNECTION & ACTIVITY", "Kicker"))
        self.activity_status = label("Ready to connect", "Muted", True)
        activity_status_font = self.activity_status.font()
        activity_status_font.setPointSize(11)
        self.activity_status.setFont(activity_status_font)
        activity_l.addWidget(self.activity_status)
        self.activity_details = label("No active match yet.", "Hint", True)
        activity_l.addWidget(self.activity_details)
        key_row = QHBoxLayout()
        self.key_state = label("HENRIK KEY: NOT SAVED", "Hint")
        key_row.addWidget(self.key_state)
        key_row.addStretch()
        key_row.addWidget(button("SETTINGS", self.open_settings))
        activity_l.addLayout(key_row)
        right.addStretch()

        # Post-match repeated-opponent checks. Never triggered by automatic refresh.
        self.pattern_panel, pattern_l = panel()
        layout.addWidget(self.pattern_panel)
        pattern_header = QHBoxLayout()
        ph = QVBoxLayout()
        ph.setSpacing(4)
        ph.addWidget(label("HISTORICAL PATTERN CHECK", "Kicker"))
        ph.addWidget(label("Repeated-opponent patterns", "SectionTitle"))
        pattern_header.addLayout(ph)
        pattern_header.addStretch()
        self.pattern_badge = label("NOT SCANNED", "AlertPill")
        pattern_header.addWidget(self.pattern_badge)
        pattern_l.addLayout(pattern_header)
        pattern_l.addWidget(label(
            "Checks up to 10 recent Competitive matches per authorized teammate. "
            "Flags any opponent encountered 4+ times on the other team. "
            "A repeat is NOT evidence of wintrading.", "Muted", True))
        pattern_l.addWidget(separator())
        pattern_l.addWidget(label("CHOOSE PLAYERS WHO HAVE AUTHORIZED HISTORY ANALYSIS", "Kicker"))
        self.pattern_players_host = QWidget()
        self.pattern_players_layout = QGridLayout(self.pattern_players_host)
        self.pattern_players_layout.setContentsMargins(0, 4, 0, 4)
        self.pattern_players_layout.setSpacing(8)
        pattern_l.addWidget(self.pattern_players_host)
        self.permission_box = QCheckBox("I confirm these selected players opted in to sharing their match histories.")
        self.permission_box.setChecked(False)
        pattern_l.addWidget(self.permission_box)
        pattern_controls = QHBoxLayout()
        self.pattern_run = button("◎  CHECK SELECTED HISTORIES", self.check_patterns, "Teal", 44)
        pattern_controls.addWidget(self.pattern_run)
        pattern_controls.addStretch()
        self.pattern_summary = label("No history analysis started", "Hint", True)
        pattern_controls.addWidget(self.pattern_summary)
        pattern_l.addLayout(pattern_controls)
        self.pattern_results_host = QWidget()
        self.pattern_results_layout = QVBoxLayout(self.pattern_results_host)
        self.pattern_results_layout.setContentsMargins(0, 0, 0, 0)
        self.pattern_results_layout.setSpacing(9)
        pattern_l.addWidget(self.pattern_results_host)
        pattern_l.addWidget(label(
            "Uses PUUIDs for counting, but does not expose opponents' names or IDs. "
            "The permission checkbox is a manual acknowledgement, not Riot verification. "
            "For compliant distribution, implement Riot RSO consent checks.", "Hint", True))
        self._build_name_history_panel(layout)
        layout.addWidget(label("UNOFFICIAL CLIENT ENDPOINTS  •  PERSONAL EXPERIMENTAL TOOL  •  ACCOUNT POLICY RISK", "Hint"))
        self.update_key_indicator()


    # ============================================
    # Historical ID viewer (local evidence only)
    # ============================================

    def _build_name_history_panel(self, container: QVBoxLayout):
        self.history_panel, l = panel()
        container.addWidget(self.history_panel)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(4)
        titles.addWidget(label("HISTORICAL MATCH SNAPSHOTS", "Kicker"))
        titles.addWidget(label("Riot ID history", "SectionTitle"))
        header.addLayout(titles)
        header.addStretch()
        self.history_badge = label("NO SNAPSHOTS", "AlertPill")
        header.addWidget(self.history_badge)
        l.addLayout(header)
        l.addWidget(label(
            "Record the Riot ID that an OLD match actually displays, along with its Episode / Act, "
            "date, match ID, and optional evidence link. Import matching CSV/JSON snapshots to compare "
            "periods automatically. This does not automatically scrape VTL or resolve old names from a current PUUID.",
            "Muted", True))
        l.addWidget(separator())

        account_row = QHBoxLayout()
        account_row.addWidget(label("YOUR PUUID", "Kicker"))
        self.history_puuid = QLineEdit()
        self.history_puuid.setPlaceholderText("Your own account PUUID (same for every observation)")
        self.history_puuid.setToolTip("Historical snapshots are grouped by account PUUID, not by username.")
        account_row.addWidget(self.history_puuid, 1)
        account_row.addWidget(button("USE MY ACCOUNT", self.use_my_history_account))
        l.addLayout(account_row)
        self.history_account_note = label("Your account only · No automatic third-party history collection", "Hint", True)
        l.addWidget(self.history_account_note)

        l.addWidget(label("ADD A HISTORICAL MATCH OBSERVATION", "Kicker"))
        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(9)
        self.history_id_input = QLineEdit()
        self.history_id_input.setPlaceholderText("Old Riot ID · e.g. OldHandle#NA1")
        self.history_act_input = QLineEdit()
        self.history_act_input.setPlaceholderText("Episode 8 Act 3")
        self.history_date_input = QLineEdit()
        self.history_date_input.setPlaceholderText("YYYY-MM-DD")
        self.history_match_input = QLineEdit()
        self.history_match_input.setPlaceholderText("Historical match ID")
        self.history_url_input = QLineEdit()
        self.history_url_input.setPlaceholderText("https://… link to the match (optional)")
        form.addWidget(self.history_id_input, 0, 0)
        form.addWidget(self.history_act_input, 0, 1)
        form.addWidget(self.history_date_input, 1, 0)
        form.addWidget(self.history_match_input, 1, 1)
        form.addWidget(self.history_url_input, 2, 0, 1, 2)
        l.addLayout(form)
        buttons = QHBoxLayout()
        buttons.setSpacing(9)
        buttons.addWidget(button("+  ADD OBSERVATION", self.add_history_record, "Primary", 42))
        buttons.addWidget(button("IMPORT CSV / JSON", self.import_history))
        buttons.addWidget(button("EXPORT", self.export_history))
        buttons.addWidget(button("EXAMPLE DATA", self.load_history_example))
        buttons.addWidget(button("CLEAR", self.clear_history))
        buttons.addStretch()
        l.addLayout(buttons)
        self.history_message = label("No historical matches entered yet. Start with one match from each Act.", "Hint", True)
        l.addWidget(self.history_message)
        l.addWidget(separator())

        self.history_results_layout = QVBoxLayout()
        self.history_results_layout.setSpacing(10)
        l.addLayout(self.history_results_layout)
        foot = QHBoxLayout()
        foot.addWidget(label("Dates are first/last OBSERVED, not verified rename dates.", "Hint", True), 1)
        foot.addWidget(button("OPEN VTL.LOL", lambda: QDesktopServices.openUrl(QUrl("https://vtl.lol"))))
        l.addLayout(foot)
        self.render_name_history()

    def use_my_history_account(self):
        person = next((p for p in self.current.allies if p.is_self and p.puuid), None)
        if person is None:
            QMessageBox.information(self, "ValIntel", "Your account PUUID isn't available in the current roster. "
                                    "Join a lobby first, or paste your own PUUID manually.")
            return
        self.history_puuid.setText(person.puuid)
        self.history_account_note.setText("Using your connected VALORANT account. History is stored only in this session unless exported.")

    def _history_owner(self) -> str:
        owner = self.history_puuid.text().strip().lower()
        if not owner:
            raise ValueError("Enter your own PUUID or use USE MY ACCOUNT first.")
        if self.history_records and self.history_records[0].puuid != owner:
            raise ValueError("Current entries belong to a different PUUID. Export/clear before switching accounts.")
        return owner

    def add_history_record(self):
        try:
            owner = self._history_owner()
            entry = normalize_observation({
                "puuid": owner, "riot_id": self.history_id_input.text(),
                "episode_act": self.history_act_input.text(),
                "match_date": self.history_date_input.text(),
                "match_id": self.history_match_input.text(),
                "source_url": self.history_url_input.text(),
            }, owner)
            updated = consolidate([*self.history_records, entry])
            self.history_records = updated
            self.history_message.setText(f"Saved observation from {entry.episode_act} · {entry.match_date} (in memory)")
            self.history_id_input.clear()
            self.history_match_input.clear()
            self.history_url_input.clear()
            self.render_name_history()
        except (ValueError, OSError) as err:
            QMessageBox.warning(self, "Invalid observation", str(err))

    def import_history(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import historical match snapshots", "",
                                              "History manifests (*.json *.csv)")
        if not path:
            return
        try:
            owner = self._history_owner()
            imported = read_observations(path, owner)
            if not imported:
                raise ValueError("File contained no observations.")
            self.history_records = consolidate([*self.history_records, *imported])
            self.render_name_history()
            self.history_message.setText(f"Imported {len(imported)} observations from {Path(path).name}. "
                                         "Check source links to verify historical names.")
        except (ValueError, OSError, UnicodeError) as err:
            QMessageBox.warning(self, "Import failed", str(err))

    def export_history(self):
        if not self.history_records:
            QMessageBox.information(self, "No observations", "Add at least one historical match first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export historical observations", "ValIntel_name_history.json",
                                              "JSON history (*.json);;CSV history (*.csv)")
        if not path:
            return
        if not Path(path).suffix:
            path += ".json"
        try:
            write_observations(path, self.history_records)
            self.history_message.setText(f"Exported {len(self.history_records)} snapshots to {Path(path).name}")
        except (ValueError, OSError) as err:
            QMessageBox.warning(self, "Export failed", str(err))

    def clear_history(self):
        if not self.history_records:
            return
        if QMessageBox.question(self, "Clear snapshots", "Clear all in-memory historical observations? "
                                "Any exported files will remain unchanged.") != QMessageBox.StandardButton.Yes:
            return
        self.history_records = []
        self.history_message.setText("In-memory observations cleared.")
        self.render_name_history()

    def load_history_example(self):
        if self.history_records and QMessageBox.question(
            self, "Replace observations", "Replace current entries with fictional example data?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.history_records = example_observations()
        self.history_puuid.setText("demo-self-account")
        self.history_message.setText("DEMO ONLY · Fictional names, match IDs and dates · no requests sent")
        self.render_name_history()

    def render_name_history(self):
        self._clear_layout(self.history_results_layout)
        entries = consolidate(self.history_records)
        if not entries:
            self.history_badge.setText("NO SNAPSHOTS")
            self.history_results_layout.addWidget(label(
                "Nothing to compare yet. Add one snapshot per Act, or import a previously exported CSV/JSON file.",
                "Hint", True))
            return
        self.history_badge.setText(f"{len(entries)} MATCHES  ·  {len({x.riot_id.casefold() for x in entries})} NAMES")
        header = label("OBSERVED NAME-CHANGE WINDOWS", "Kicker")
        self.history_results_layout.addWidget(header)
        windows = changes(entries)
        if not windows:
            self.history_results_layout.addWidget(label(
                "No name changes observed in the supplied match snapshots. This does not prove there were none.",
                "Hint", True))
        for window in reversed(windows):
            card, content = panel("Inset")
            content.addWidget(label(f"{window.prior_id}  →  {window.next_id}", "SectionTitle"))
            content.addWidget(label(
                f"Last saw old ID: {window.last_seen_prior} ({window.prior_act})   •   "
                f"First saw new ID: {window.first_seen_next} ({window.next_act})", "Muted", True))
            content.addWidget(label("Rename happened somewhere BETWEEN these observations; exact date unknown.",
                                    "Hint", True))
            self.history_results_layout.addWidget(card)

        self.history_results_layout.addWidget(label("EVIDENCE BY EPISODE / ACT", "Kicker"))
        for act, group in by_act(entries):
            card, content = panel("Inset")
            row = QHBoxLayout()
            row.addWidget(label(act, "SectionTitle"))
            row.addStretch()
            row.addWidget(label(f"{len(group)} MATCHES", "Hint"))
            content.addLayout(row)
            for item in reversed(group):
                line = QHBoxLayout()
                text = label(f"{item.riot_id}   ·   {item.match_date}   ·   {item.match_id}", "Muted", True)
                line.addWidget(text, 1)
                if item.source_url:
                    line.addWidget(button("VIEW MATCH", lambda _checked=False, url=item.source_url:
                                           QDesktopServices.openUrl(QUrl(url))))
                content.addLayout(line)
            self.history_results_layout.addWidget(card)


    def update_key_indicator(self):
        self.key_state.setText("HENRIK KEY: AVAILABLE" if self.key else "HENRIK KEY: NOT SAVED")

    def scroll_to(self, widget: QWidget):
        # Main page positions may shift when images/rows change.
        self.main_scroll.ensureWidgetVisible(widget, 12, 12)

    def populate_agent_tiles(self):
        for tile in self.agent_tiles.values():
            self.grid_layout.removeWidget(tile)
            tile.deleteLater()
        self.agent_tiles.clear()
        self.agent_urls.clear()
        for name, (agent_id, url) in sorted(self.agent_items.items(), key=lambda item: item[0].casefold()):
            tile = AgentTile(name, agent_id)
            tile.clicked.connect(self.choose_agent)
            self.agent_tiles[name] = tile
            self.agent_urls[name] = url
            self.queue_icon(url)
        self.filter_agents()
        self.sync_agent_selection()
        self.agent_count.setText(f"{len(self.agent_items)} AGENTS")

    def filter_agents(self, *args):
        query = self.search.text().strip().lower()
        role = self.role_filter.currentText()
        shown = [name for name in sorted(self.agent_tiles, key=str.casefold)
                 if query in name.lower() and (role == "ALL ROLES" or ROLE.get(name) == role)]
        for tile in self.agent_tiles.values():
            self.grid_layout.removeWidget(tile)
            tile.hide()
        available = self.agent_grid_scroll.viewport().width()
        columns = max(3, min(7, (max(320, available) - 12) // 104))
        for index, name in enumerate(shown):
            tile = self.agent_tiles[name]
            row, column = divmod(index, columns)
            self.grid_layout.addWidget(tile, row, column)
            tile.show()
        # Reflow automatically when the main window changes width.

    def queue_icon(self, url: str):
        if (not url or not url.startswith("https://media.valorant-api.com/agents/")
                or url in self.icon_pixmaps or url in self.icon_pending or url in self.icon_failed):
            return
        self.icon_pending.add(url)

        def work():
            data = None
            # Store portrait downloads outside the extracted PyInstaller executable.
            try:
                agent_id = url.split("/agents/", 1)[1].split("/", 1)[0]
                cache = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ValIntel" / "agent_icons" / f"{agent_id.lower()}.png"
                if cache.is_file():
                    data = cache.read_bytes()
                if not data:
                    data = fetch_agent_icon(url)
                    if data:
                        cache.parent.mkdir(parents=True, exist_ok=True)
                        cache.write_bytes(data)
            except (OSError, ValueError):
                if not data:
                    data = fetch_agent_icon(url)
            if not self.closed:
                self.bridge.portrait.emit(url, data)

        self.icon_pool.submit(work)

    def on_portrait(self, url: str, raw):
        self.icon_pending.discard(url)
        if not raw:
            self.icon_failed.add(url)
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(raw):
            self.icon_failed.add(url)
            return
        self.icon_pixmaps[url] = pixmap
        self.icon_failed.discard(url)
        for name, agent_url in self.agent_urls.items():
            if agent_url == url and name in self.agent_tiles:
                self.agent_tiles[name].set_portrait(pixmap)
        for player_row in self.live_icon_rows.get(url, []):
            player_row.set_icon(pixmap)
        if url == self.selected_url:
            self.update_selected_portrait()

    def retry_icons(self):
        self.icon_failed.clear()
        for url in self.agent_urls.values():
            self.queue_icon(url)
        self.set_feedback("Retrying missing portraits…")

    def _load_agent_catalog_async(self):
        def work():
            try:
                data = {name: (uid, url) for uid, (name, url) in self.catalog_api.agent_catalog().items()}
                if not self.closed:
                    self.bridge.catalog.emit(data)
            except Exception:
                pass
        threading.Thread(target=work, daemon=True, name="ValIntelCatalog").start()

    def on_catalog(self, items):
        if items != self.agent_items:
            # Agent catalog only builds selector UI. Keep current selection by UUID.
            self.agent_items = items
            self.populate_agent_tiles()
        else:
            self.agent_count.setText(f"{len(self.agent_items)} AGENTS  ·  SYNCED")

    def choose_agent(self, name: str):
        if name not in self.agent_items:
            return
        if self.action_busy:
            self.set_feedback("Agent action in progress. Complete it before switching.", "warning")
            return
        if self.lock_deadline is not None:
            self.cancel_lock("Countdown canceled because you changed agents.")
        self.selected_name = name
        self.selected_id, self.selected_url = self.agent_items[name]
        self.sync_agent_selection()
        if self.demo:
            self.set_feedback(f"Preview: {name} chosen. No Riot request sent (Demo Mode).")
            return
        self.action_busy = True
        self.update_lock_button()
        self.set_feedback(f"Selecting {name} in the active lobby…")
        agent_id = self.selected_id

        def work():
            try:
                result = self.lock_api.select_agent(agent_id)
                self.bridge.event.emit(("action", "select", name, str(result), None))
            except Exception as exc:
                self.bridge.event.emit(("action", "select", name, None, str(exc)))
        threading.Thread(target=work, daemon=True, name="ValIntelSelect").start()

    def sync_agent_selection(self):
        for name, tile in self.agent_tiles.items():
            tile.set_selected(name == self.selected_name)
        self.selected_agent_name.setText(self.selected_name or "No agent selected")
        self.selected_role.setText(ROLE.get(self.selected_name, "SELECT FROM THE GRID"))
        self.update_selected_portrait()
        self.update_lock_button()

    def update_selected_portrait(self):
        self.selected_portrait.clear()
        if self.selected_url in self.icon_pixmaps:
            pixmap = self.icon_pixmaps[self.selected_url].scaled(
                88, 91, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            self.selected_portrait.setPixmap(pixmap)
        else:
            self.selected_portrait.setText((self.selected_name or "?")[:1].upper())

    def update_lock_button(self):
        if self.lock_deadline is not None:
            self.lock_button.setText("CANCEL LOCK")
            self.lock_button.setEnabled(True)
        elif self.action_busy:
            self.lock_button.setText("REQUEST IN PROGRESS…")
            self.lock_button.setEnabled(False)
        else:
            self.lock_button.setText("LOCK NOW  ·  3 SEC")
            self.lock_button.setEnabled(bool(self.selected_id) and not self.demo)

    def set_feedback(self, text: str, level="info"):
        self.last_message = text
        self.agent_feedback.setText(text)
        color = {"warning": PALETTE["yellow"], "error": "#FF919A", "success": PALETTE["green"]}.get(level, "#B6C6D6")
        self.agent_feedback.setStyleSheet(f"color: {color}; font-size: 12px;")

    def handle_lock_button(self):
        if self.lock_deadline is not None:
            self.cancel_lock("Lock canceled — no request sent.")
            return
        if self.action_busy or not self.selected_id or self.demo:
            return
        self.pending_agent = (self.selected_name, self.selected_id)
        self.lock_deadline = time.monotonic() + 3.0
        self.lock_progress.setValue(0)
        self.set_feedback(f"{self.selected_name} will lock in 3.0 seconds. Press CANCEL to stop.")
        self.update_lock_button()

    def cancel_lock(self, reason="Lock canceled"):
        self.lock_deadline = None
        self.pending_agent = None
        self.lock_progress.setValue(0)
        self.set_feedback(reason)
        self.update_lock_button()

    def _issue_lock(self, name, agent_id):
        self.action_busy = True
        self.update_lock_button()
        self.set_feedback(f"Sending one lock request for {name}…")

        def work():
            try:
                ctx = self.lock_api.probe_pregame()
                if not ctx or ctx.get("state") != "character_select_active":
                    raise RuntimeError("No active agent-selection lobby detected")
                result = self.lock_api.lock_agent(ctx["match_id"], agent_id)
                self.bridge.event.emit(("action", "lock", name, str(result), None))
            except Exception as exc:
                self.bridge.event.emit(("action", "lock", name, None, str(exc)))
        threading.Thread(target=work, daemon=True, name="ValIntelLock").start()

    def tick(self):
        if self.lock_deadline is not None and self.pending_agent:
            remaining = self.lock_deadline - time.monotonic()
            if remaining > 0:
                elapsed = max(0.0, 3.0 - remaining)
                self.lock_progress.setValue(round(100 * elapsed / 3.0))
                self.agent_feedback.setText(
                    f"{self.pending_agent[0]} — locking in {remaining:.1f}s. Press CANCEL LOCK to stop."
                )
            else:
                name, agent_id = self.pending_agent
                self.lock_deadline = None
                self.pending_agent = None
                self.lock_progress.setValue(100)
                self._issue_lock(name, agent_id)
        if (self.auto_refresh and not self.demo and not self.refresh_busy and
                time.monotonic() - self.last_refresh > REFRESH_SECONDS):
            self.refresh()

    def toggle_demo(self):
        self.demo = not self.demo
        if self.lock_deadline is not None:
            self.cancel_lock("Countdown canceled — switched modes.")
        self.demo_button.setText("EXIT DEMO" if self.demo else "DEMO MODE")
        if self.demo:
            self.refresh_token += 1
            self.render_snapshot(demo_snapshot())
            self.set_feedback("Demo Mode: agent actions are previews only, with no Riot requests.")
        else:
            self.render_snapshot(Snapshot(status="Returning to live mode…"))
            if self.refresh_busy:
                self.pending_refresh = True
            else:
                self.refresh()
        self.update_lock_button()

    def refresh(self, force_analysis=False):
        if self.demo:
            self.render_snapshot(demo_snapshot())
            return
        if self.refresh_busy:
            if force_analysis:
                self.after_refresh = True
            return
        if os.name != "nt":
            self.render_snapshot(Snapshot(status="Live mode needs Windows; use Demo Mode.",
                                          error="Riot Client integration requires Windows."))
            return
        self.refresh_busy = True
        self.last_refresh = time.monotonic()
        self.refresh_token += 1
        token = self.refresh_token
        self.activity_status.setText("Scanning VALORANT match…")
        key = self.key
        stats_on = self.stats_on

        def work():
            try:
                glz, pd, headers, puuid = self.api.connect()
                snap, _ = self.api.fetch_roster(glz, headers, puuid)
                if snap.error:
                    self.bridge.event.emit(("snapshot", token, copy.deepcopy(snap)))
                    return
                self.api.fill_agents(snap)
                self.bridge.event.emit(("snapshot", token, copy.deepcopy(snap)))
                self.api.fill_names(snap, pd, headers, key)
                self.bridge.event.emit(("snapshot", token, copy.deepcopy(snap)))
                if stats_on and snap.mode == "IN GAME" and snap.match_id and (
                        force_analysis or snap.match_id not in self.attempted_stats):
                    self.attempted_stats.add(snap.match_id)
                    self.bridge.event.emit(("status", token, "Loading recent Competitive stats…"))
                    self.api.fill_stats(snap, key)
                    self.bridge.event.emit(("snapshot", token, copy.deepcopy(snap)))
            except Exception as exc:
                self.bridge.event.emit(("error", token, str(exc)))
            finally:
                self.bridge.event.emit(("refresh_done", token))

        threading.Thread(target=work, daemon=True, name="ValIntelRoster").start()

    def analyze_match(self):
        if self.demo:
            self.render_snapshot(demo_snapshot())
            return
        if not self.stats_on:
            self.stats_on = True
            self.settings_store.setValue("stats_enabled", True)
        if not self.key:
            QMessageBox.information(self, "API key needed", "Save a HenrikDEV API key in Settings to request match histories.")
            self.open_settings()
            return
        if self.current.mode != "IN GAME":
            self.analysis_message.setText("Opponent comparison becomes available after the match starts.")
            return
        self.analysis_message.setText("Fetching recent match histories…")
        self.refresh(force_analysis=True)

    def on_event(self, message):
        kind = message[0]
        if kind in ("pattern_result", "pattern_error", "pattern_done"):
            _, token, match_id, *payload = message
            if token != self.pattern_token or match_id != self.current.match_id:
                return
            if kind == "pattern_result":
                self.pattern_results.append(payload[0])
                self.render_pattern_results()
                self.pattern_summary.setText(f"{len(self.pattern_results)} player histories processed")
            elif kind == "pattern_error":
                self.pattern_summary.setText(f"Analysis error: {payload[0]}")
            else:
                self.pattern_running = False
                self.pattern_run.setEnabled(True)
                self.render_pattern_results()
            return
        if kind == "action":
            _, action, name, result, error = message
            self.action_busy = False
            if error:
                self.set_feedback(f"{action.title()} failed: {error[:320]}", "error")
            else:
                self.set_feedback(f"{name}: {result}", "success")
                if not self.demo:
                    self.refresh()
            self.lock_progress.setValue(0)
            self.update_lock_button()
            return
        if kind == "snapshot":
            _, token, snap = message
            if token == self.refresh_token and not self.demo:
                self.render_snapshot(snap)
        elif kind == "status":
            _, token, message_text = message
            if token == self.refresh_token and not self.demo:
                self.activity_status.setText(message_text)
        elif kind == "error":
            _, token, err = message
            if token == self.refresh_token and not self.demo:
                self.render_snapshot(Snapshot(status="Connection failed", error=err))
        elif kind == "refresh_done":
            _, token = message
            # Even a stale result must release the busy state after a Demo toggle.
            self.refresh_busy = False
            self.last_refresh = time.monotonic()
            if self.after_refresh:
                self.after_refresh = False
                QTimer.singleShot(50, lambda: self.refresh(force_analysis=True))
            elif self.pending_refresh and not self.demo:
                self.pending_refresh = False
                QTimer.singleShot(50, self.refresh)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def _selected_pattern_players(self):
        # Copies keep the worker isolated from live roster re-rendering.
        return [copy.deepcopy(p) for p in self.current.allies
                if p.puuid in self.pattern_selection]

    def _toggle_pattern_player(self, puuid: str, enabled: bool):
        if enabled:
            self.pattern_selection.add(puuid)
        else:
            self.pattern_selection.discard(puuid)

    def render_pattern_players(self, snap: Snapshot):
        self._clear_layout(self.pattern_players_layout)
        self.pattern_checkboxes = {}
        if not snap.allies:
            self.pattern_players_layout.addWidget(label("Enter a match to see teammates.", "Hint"), 0, 0)
            return
        for index, player in enumerate(snap.allies):
            display = player.name if player.name and player.name != "Resolving…" else player.agent
            if player.is_self:
                display += "  (you)"
            checkbox = QCheckBox(display[:50])
            checkbox.setChecked(player.puuid in self.pattern_selection)
            checkbox.toggled.connect(lambda enabled, puuid=player.puuid:
                                     self._toggle_pattern_player(puuid, enabled))
            self.pattern_players_layout.addWidget(checkbox, index // 3, index % 3)
            self.pattern_checkboxes[player.puuid] = checkbox

    def render_pattern_results(self):
        self._clear_layout(self.pattern_results_layout)
        if not self.pattern_results:
            self.pattern_badge.setText("NOT SCANNED")
            self.pattern_results_layout.addWidget(label(
                "Results will appear here after a manual history check.", "Hint"))
            return
        flagged = sum(bool(r.findings) for r in self.pattern_results)
        complete = sum(r.status == "complete" for r in self.pattern_results)
        self.pattern_badge.setText("NO DATA" if not any(r.checked for r in self.pattern_results) else
                                   f"{flagged} PATTERN{'S' if flagged != 1 else ''} FOUND")
        self.pattern_summary.setText(f"{complete}/{len(self.pattern_results)} complete histories")
        for result in self.pattern_results:
            card = QFrame()
            card.setObjectName("Inset")
            card_l = QVBoxLayout(card)
            card_l.setContentsMargins(14, 12, 14, 12)
            card_l.setSpacing(6)
            heading = QHBoxLayout()
            heading.addWidget(label(result.player_name, "StatValue"))
            heading.addStretch()
            state = label(f"{result.checked}/{result.requested} matches  ·  {result.status.upper()}")
            state.setStyleSheet(
                f"color: {'#F9BD74' if result.status != 'complete' else '#72E4AC'}; "
                "font-size: 11px; font-weight: 700;")
            heading.addWidget(state)
            card_l.addLayout(heading)
            card_l.addWidget(label(result.explanation, "Hint", True))
            if result.findings:
                for repeat in result.findings:
                    txt = (f"{repeat.label}  •  {repeat.encounters}/{result.checked} opposing encounters  ·  "
                           f"W {repeat.player_wins} / L {repeat.player_losses}")
                    finding = label(txt, "Muted", True)
                    finding.setStyleSheet("color: #F9BD74; font-weight: 700; font-size: 12px;")
                    card_l.addWidget(finding)
            elif result.status != "unavailable":
                card_l.addWidget(label(
                    "No repeated opponent reached 4 encounters in the available sample.", "Hint", True))
            self.pattern_results_layout.addWidget(card)

    def check_patterns(self):
        if self.pattern_running:
            return
        selected = self._selected_pattern_players()
        if not selected:
            QMessageBox.information(self, "Choose players", "Select the teammates who gave permission to analyze their histories.")
            return
        if not self.permission_box.isChecked():
            QMessageBox.information(self, "Player consent required",
                                    "Confirm that each selected player opted in before fetching their match history.")
            return
        if self.demo:
            self.pattern_results = demo_reports()
            self.render_pattern_results()
            self.pattern_summary.setText("Demo patterns only — no API calls")
            return
        if not self.key:
            QMessageBox.information(self, "HenrikDEV key needed", "Add your API key in Settings first.")
            return
        if self.current.mode not in ("PREGAME", "IN GAME") or not self.current.match_id:
            QMessageBox.information(self, "Match not detected", "Connect to a VALORANT match first.")
            return
        # Historical analysis only; never automatically run during agent selection.
        if self.current.mode == "PREGAME":
            QMessageBox.information(self, "Post-match analysis",
                                    "Historical checks are only enabled after entering a match, not during agent selection.")
            return
        self.pattern_token += 1
        token = self.pattern_token
        original_match_id = self.current.match_id
        self.pattern_running = True
        self.pattern_results = []
        self.pattern_run.setEnabled(False)
        self.pattern_badge.setText("SCANNING")
        self.pattern_summary.setText(f"0/{len(selected)} histories checked")
        self._clear_layout(self.pattern_results_layout)
        self.pattern_results_layout.addWidget(label("Checking histories sequentially…", "Hint"))
        key = self.key
        region = self.api.region

        def worker():
            api = RiotAPI()
            try:
                def on_result(report):
                    self.bridge.event.emit(("pattern_result", token, original_match_id, report))
                scan_players(selected, key, region, api.henrik, on_result=on_result)
            except Exception as exc:
                self.bridge.event.emit(("pattern_error", token, original_match_id, str(exc)[:160]))
            finally:
                self.bridge.event.emit(("pattern_done", token, original_match_id))
        threading.Thread(target=worker, daemon=True, name="ValIntelPatternCheck").start()

    def render_snapshot(self, snap: Snapshot):
        if snap.match_id != self.pattern_match_id:
            self.pattern_match_id = snap.match_id
            self.pattern_selection.clear()
            self.pattern_results = []
            self.pattern_token += 1
            self.pattern_running = False
            self.pattern_run.setEnabled(True)
            self.permission_box.setChecked(False)
            self.pattern_summary.setText("No history analysis started")
            self.render_pattern_results()
        self.current = snap
        self.render_pattern_players(snap)
        mode = snap.mode if not self.demo else "DEMO"
        connected = mode in ("PREGAME", "IN GAME", "DEMO")
        self.mode_pill.setText(f"●  {mode if connected else 'WAITING'}")
        self.mode_pill.setObjectName("Pill" if connected else "AlertPill")
        self.mode_pill.style().unpolish(self.mode_pill)
        self.mode_pill.style().polish(self.mode_pill)
        self.side_connection.setText("●  MATCH CONNECTED" if connected else "●  NOT CONNECTED")
        self.side_connection.setStyleSheet(
            f"color: {'#72E4AC' if connected else '#F6BE7C'}; font-weight: 800; font-size: 11px;"
        )
        self.map_label.setText(f"{snap.map_name}   ·   {mode}" if snap.match_id else snap.status)
        self.count_label.setText(f"{len(snap.allies) + len(snap.enemies)} PLAYERS")
        self.ally_title.setText(f"●  YOUR TEAM  /  {len(snap.allies)} PLAYERS")
        self.enemy_title.setText(f"●  OPPONENTS  /  {len(snap.enemies)} PLAYERS")
        self.live_icon_rows.clear()
        self._populate_roster(self.allies_box, snap.allies, "#72E4AC", "Waiting for your team…")
        if mode == "PREGAME":
            empty = "Opponent identities are unavailable in agent selection."
        else:
            empty = "Opponents will appear once a team-based match starts."
        self._populate_roster(self.enemies_box, snap.enemies, "#FF6976", empty)
        if snap.mode == "PREGAME" and not self.action_busy and self.lock_deadline is None:
            own = next((p for p in snap.allies if p.is_self and p.agent_id), None)
            if own:
                for name, (agent_id, url) in self.agent_items.items():
                    if agent_id.lower() == own.agent_id.lower() and name != self.selected_name:
                        self.selected_name, self.selected_id, self.selected_url = name, agent_id, url
                        self.sync_agent_selection()
                        break
        value, coverage = estimate_match(snap.allies, snap.enemies)
        self.gauge.set_value(value)
        self.coverage.setText(
            f"STATS COVERAGE   ALLY {coverage[0]}/{len(snap.allies)}  ·  ENEMY {coverage[1]}/{len(snap.enemies)}"
        )
        if value is not None:
            self.analysis_tag.setText("ESTIMATE READY")
            self.analysis_message.setText("Comparison available. Treat the result as a rough heuristic, not a true probability.")
        elif mode == "PREGAME":
            self.analysis_tag.setText("PREGAME")
            self.analysis_message.setText("Enemy roster is not exposed during agent select. Analysis starts after loading in.")
        elif not self.key:
            self.analysis_tag.setText("KEY REQUIRED")
            self.analysis_message.setText("Add your HenrikDEV key in Settings to retrieve recent stats.")
        elif snap.stats_note:
            self.analysis_tag.setText("DATA LIMITED")
            self.analysis_message.setText(snap.stats_note[:240])
        elif not self.stats_on:
            self.analysis_tag.setText("OFF")
            self.analysis_message.setText("Enable statistics in Settings or click RUN MATCH ANALYSIS.")
        else:
            self.analysis_tag.setText("WAITING")
            self.analysis_message.setText("At least three players on each team need usable recent match history.")
        self.insight_label.setText(self._make_insight(snap.allies, snap.enemies) if value is not None
                                   else "Insight details require usable recent results from both teams.")
        self.activity_status.setText(snap.status)
        self.activity_details.setText((snap.error or snap.stats_note or "Live match data updates automatically.")[:310])

    @staticmethod
    def _make_insight(allies: list[Player], enemies: list[Player]) -> str:
        def metrics(team):
            eligible = [p for p in team if p.games >= 3 and p.kd is not None
                        and p.winrate is not None]
            if not eligible:
                return None
            return (sum(p.kd for p in eligible) / len(eligible),
                    100 * sum(p.winrate for p in eligible) / len(eligible))
        ally, enemy = metrics(allies), metrics(enemies)
        if ally is None or enemy is None:
            return "Unable to compare team trends."
        kd_diff = ally[0] - enemy[0]
        wr_diff = ally[1] - enemy[1]
        edge = "Allies" if kd_diff + wr_diff / 50 >= 0 else "Opponents"
        return (f"DATA INSIGHT · {edge} show the stronger recent aggregate. "
                f"Average K/D {ally[0]:.2f} vs {enemy[0]:.2f}; "
                f"recent win rate {ally[1]:.0f}% vs {enemy[1]:.0f}%. "
                "This is a small, potentially biased sample.")

    def _populate_roster(self, layout: QVBoxLayout, players: list[Player], color: str, empty_text: str):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        if not players:
            msg = label(empty_text, "Muted", True)
            msg.setMinimumHeight(48)
            layout.addWidget(msg)
            return
        for player in players:
            row = PlayerRow(player, color, self.stats_on)
            layout.addWidget(row)
            if player.icon:
                self.live_icon_rows.setdefault(player.icon, []).append(row)
                if player.icon in self.icon_pixmaps:
                    row.set_icon(self.icon_pixmaps[player.icon])
                else:
                    self.queue_icon(player.icon)

    def open_settings(self):
        dlg = SettingsDialog(self, self.key, self.auto_refresh, self.stats_on)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        key = dlg.key_field.text().strip()
        try:
            if dlg.delete_requested or not key:
                try:
                    keyring.delete_password(CREDENTIAL_SERVICE, CREDENTIAL_USERNAME)
                except keyring.errors.PasswordDeleteError:
                    pass
            else:
                keyring.set_password(CREDENTIAL_SERVICE, CREDENTIAL_USERNAME, key)
        except Exception as exc:
            QMessageBox.warning(self, "Credential storage error", str(exc))
            return
        self.key = key
        self.auto_refresh = dlg.refresh_box.isChecked()
        self.stats_on = dlg.stats_box.isChecked()
        self.settings_store.setValue("auto_refresh", self.auto_refresh)
        self.settings_store.setValue("stats_enabled", self.stats_on)
        self.update_key_indicator()
        self.render_snapshot(self.current)
        if not self.demo:
            self.refresh()
        self.set_feedback("Settings saved.", "success")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "agent_grid_scroll"):
            QTimer.singleShot(0, self.filter_agents)

    def closeEvent(self, event):
        self.closed = True
        self.clock.stop()
        self.icon_pool.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ValIntel")
    app.setOrganizationName("ValIntel")
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
