"""ValIntel / PySide6

A standalone Qt desktop front end. The existing Riot/HenrikDEV logic lives in
backend.py; this file never sends an HTTP request on the UI thread.

Run: python ValIntelGUI.py
"""
from __future__ import annotations

import copy
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import keyring
from PySide6.QtCore import QObject, QRectF, Qt, QSettings, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from pattern_checker import PatternReport, demo_reports, scan_players

from backend import (
    AgentLockService, KNOWN_AGENTS, Player, REFRESH_SECONDS, RiotAPI,
    Snapshot, demo_snapshot, estimate_match, fetch_agent_icon,
)

APP_TITLE = "VALINTEL"
CREDENTIAL_SERVICE = "ValIntel"
CREDENTIAL_USERNAME = "HenrikDEV_API_Key"

PALETTE = {
    "bg": "#090D14", "sidebar": "#0D1420", "panel": "#121C29",
    "surface": "#182435", "surface2": "#1D2D3D", "line": "#2A3949",
    "text": "#F4F7FB", "muted": "#8B9CB0", "faint": "#617387",
    "red": "#FF4655", "red_dark": "#3C222B", "cyan": "#5AD9CF",
    "green": "#72E4AC", "yellow": "#F9BD74", "blue": "#82B9FF",
}

ROLE = {
    "Astra": "CONTROLLER", "Breach": "INITIATOR", "Brimstone": "CONTROLLER",
    "Chamber": "SENTINEL", "Clove": "CONTROLLER", "Cypher": "SENTINEL",
    "Deadlock": "SENTINEL", "Fade": "INITIATOR", "Gekko": "INITIATOR",
    "Harbor": "CONTROLLER", "Iso": "DUELIST", "Jett": "DUELIST",
    "KAY/O": "INITIATOR", "Killjoy": "SENTINEL", "Miks": "INITIATOR",
    "Neon": "DUELIST", "Omen": "CONTROLLER", "Phoenix": "DUELIST",
    "Raze": "DUELIST", "Reyna": "DUELIST", "Sage": "SENTINEL",
    "Skye": "INITIATOR", "Sova": "INITIATOR", "Tejo": "INITIATOR",
    "Veto": "SENTINEL", "Viper": "CONTROLLER", "Vyse": "SENTINEL",
    "Waylay": "DUELIST", "Yoru": "DUELIST",
}

STYLESHEET = """
* { font-family: 'Segoe UI', 'Inter', sans-serif; }
QWidget { color: #F4F7FB; background: transparent; font-size: 12px; }
QMainWindow, QWidget#Root, QScrollArea#MainScroll, QWidget#MainCanvas { background: #090D14; }
QFrame#Sidebar { background: #0D1420; border-right: 1px solid #263342; }
QFrame#Panel { background: #121C29; border: 1px solid #263647; border-radius: 15px; }
QFrame#Inset { background: #182435; border: 1px solid #27384A; border-radius: 11px; }
QFrame#Feature { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #1C283A, stop:1 #101D2C); border: 1px solid #344253; border-radius: 15px; }
QFrame#HeaderCard { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #242437, stop:0.45 #182637, stop:1 #10232A); border: 1px solid #344354; border-radius: 15px; }
QFrame#Separator { background: #283B4A; max-height: 1px; }
QLabel#Kicker { color: #8DA2B5; font-size: 10px; font-weight: 700; letter-spacing: 2px; }
QLabel#PageTitle { font-size: 27px; font-weight: 800; letter-spacing: 1px; }
QLabel#SectionTitle { font-size: 16px; font-weight: 800; }
QLabel#Muted { color: #8B9CB0; font-size: 12px; }
QLabel#Hint { color: #8095AA; font-size: 11px; }
QLabel#HeroTitle { font-size: 23px; font-weight: 800; letter-spacing: 1px; }
QLabel#BigName { font-size: 22px; font-weight: 800; }
QLabel#StatValue { font-size: 15px; font-weight: 800; }
QLabel#Pill { color: #80E5BA; background: #173A35; border: 1px solid #255B50; border-radius: 12px; padding: 5px 10px; font-size: 10px; font-weight: 800; }
QLabel#AlertPill { color: #F7BB76; background: #422E26; border: 1px solid #604632; border-radius: 12px; padding: 5px 10px; font-size: 10px; font-weight: 800; }
QPushButton { background: #1B2B3B; border: 1px solid #344657; color: #F0F4FA; border-radius: 9px; padding: 9px 15px; font-weight: 700; }
QPushButton:hover { background: #283B4C; border: 1px solid #536579; }
QPushButton:pressed { background: #14212D; }
QPushButton:disabled { color: #63778A; background: #17212D; border: 1px solid #263444; }
QPushButton#Primary { background: #FF4655; color: white; border: 1px solid #FF6873; }
QPushButton#Primary:hover { background: #FF6070; }
QPushButton#Primary:disabled { background: #523039; color: #B18E94; border: 1px solid #603C46; }
QPushButton#Teal { background: #1B4242; color: #71E7D2; border: 1px solid #2B7A75; }
QPushButton#Teal:hover { background: #285751; }
QPushButton#Nav { text-align: left; background: transparent; border: 1px solid transparent; padding: 12px 14px; color: #8B9CB0; font-weight: 600; }
QPushButton#Nav:hover { background: #1A2938; color: #F4F7FB; }
QPushButton#NavActive { text-align: left; background: #202D40; border: 1px solid #334758; border-left: 3px solid #FF4655; padding: 12px 14px; color: white; font-weight: 800; }
QLineEdit, QComboBox { background: #101A27; border: 1px solid #324458; border-radius: 9px; padding: 10px 12px; selection-background-color: #FF4655; color: white; }
QLineEdit:focus, QComboBox:focus { border: 1px solid #5AD9CF; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: #162433; color: white; border: 1px solid #344657; selection-background-color: #31485C; }
QCheckBox { color: #D5E0EA; spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #607082; border-radius: 4px; background: #0D1723; }
QCheckBox::indicator:checked { background: #FF4655; border: 1px solid #FF4655; image: none; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: #111A27; width: 8px; margin: 2px; border-radius: 4px; }
QScrollBar::handle:vertical { background: #3D5063; border-radius: 4px; min-height: 32px; }
QScrollBar:horizontal { background: #111A27; height: 8px; margin: 2px; border-radius: 4px; }
QScrollBar::handle:horizontal { background: #3D5063; border-radius: 4px; min-width: 32px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0px; width: 0px; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
QProgressBar { background: #253344; border: none; border-radius: 4px; height: 8px; text-align: center; }
QProgressBar::chunk { background: #FF4655; border-radius: 4px; }
QDialog { background: #111B28; }
"""


def label(text: str, kind: str = "", word_wrap: bool = False) -> QLabel:
    w = QLabel(text)
    if kind:
        w.setObjectName(kind)
    w.setWordWrap(word_wrap)
    return w


def button(text: str, callback, variant: str = "", height: int = 38) -> QPushButton:
    b = QPushButton(text)
    if variant:
        b.setObjectName(variant)
    b.setMinimumHeight(height)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.clicked.connect(callback)
    return b


def panel(name="Panel") -> tuple[QFrame, QVBoxLayout]:
    p = QFrame()
    p.setObjectName(name)
    l = QVBoxLayout(p)
    l.setContentsMargins(20, 19, 20, 20)
    l.setSpacing(12)
    return p, l


def separator() -> QFrame:
    s = QFrame()
    s.setObjectName("Separator")
    s.setFixedHeight(1)
    return s


def get_key() -> str:
    try:
        return keyring.get_password(CREDENTIAL_SERVICE, CREDENTIAL_USERNAME) or ""
    except Exception:
        return ""


class Bridge(QObject):
    """Cross-thread delivery. Qt executes receivers on the GUI thread."""
    event = Signal(object)
    portrait = Signal(str, object)
    catalog = Signal(object)


class Gauge(QWidget):
    def __init__(self):
        super().__init__()
        self.value: int | None = None
        self.setMinimumSize(200, 196)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_value(self, value: int | None):
        self.value = value
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        edge = min(self.width(), self.height()) - 34
        rect = QRectF((self.width() - edge) / 2, 15, edge, edge)
        painter.setPen(QPen(QColor("#293C4C"), 13, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(rect, 0, 360 * 16)
        if self.value is not None:
            color = "#71E4AE" if self.value >= 50 else "#FF6571"
            painter.setPen(QPen(QColor(color), 13, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(rect, 90 * 16, int(-360 * 16 * (self.value / 100)))
        painter.setPen(QColor("#F3F6FB"))
        painter.setFont(QFont("Segoe UI", 37, QFont.Weight.Bold))
        painter.drawText(rect.adjusted(0, -1, 0, -5), Qt.AlignmentFlag.AlignCenter,
                         "—" if self.value is None else f"{self.value}%")
        painter.setPen(QColor("#8B9CB0"))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        sub = QRectF(rect.left(), rect.bottom() - 41, rect.width(), 24)
        painter.drawText(sub, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                         "ALLY WIN ESTIMATE" if self.value is not None else "AWAITING STATS")


class AgentTile(QFrame):
    clicked = Signal(str)

    def __init__(self, name: str, agent_id: str):
        super().__init__()
        self.agent_name = name
        self.agent_id = agent_id
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(96, 104)
        self.setObjectName("AgentTile")
        self.setProperty("selected", False)
        self._selected = False
        self._draw_style()
        col = QVBoxLayout(self)
        col.setContentsMargins(4, 7, 4, 5)
        col.setSpacing(2)
        self.picture = QLabel(name[:1].upper())
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.picture.setFixedSize(84, 65)
        self.picture.setStyleSheet("font-size: 30px; font-weight: 800; color: #9BB4C8;")
        self.picture.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        col.addWidget(self.picture, 0, Qt.AlignmentFlag.AlignCenter)
        self.name_label = QLabel(name)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setStyleSheet("font-size: 10px; font-weight: 700; color: #CEDAE5;")
        self.name_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        col.addWidget(self.name_label)

    def _draw_style(self):
        border = "#64E3CA" if self._selected else "#2A3A4D"
        bg = "#214343" if self._selected else "#192635"
        self.setStyleSheet(f"QFrame#AgentTile {{ background: {bg}; border: 1px solid {border}; border-radius: 11px; }}"
                           f"QFrame#AgentTile:hover {{ background: #2C414B; border-color: #7FC7C9; }}")

    def set_selected(self, active: bool):
        self._selected = active
        self._draw_style()
        self.name_label.setStyleSheet(
            f"font-size: 10px; font-weight: 800; color: {'#7EEDDB' if active else '#CEDAE5'};"
        )

    def set_portrait(self, pixmap: QPixmap):
        self.picture.setPixmap(pixmap.scaled(67, 63, Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation))
        self.picture.setStyleSheet("background: transparent; border: none;")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.agent_name)
        super().mousePressEvent(event)


class PlayerRow(QFrame):
    def __init__(self, player: Player, color: str, show_stats: bool):
        super().__init__()
        self.player = player
        self.setObjectName("Inset")
        self.setMinimumHeight(62)
        horizontal = QHBoxLayout(self)
        horizontal.setContentsMargins(10, 7, 11, 7)
        horizontal.setSpacing(10)
        self.icon_label = QLabel((player.agent or "?")[:1].upper())
        self.icon_label.setFixedSize(42, 46)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet(f"background: #203346; border: 1px solid #3A5265; border-radius: 7px; color: {color}; font-size: 18px; font-weight: 800;")
        horizontal.addWidget(self.icon_label)
        names = QVBoxLayout()
        names.setSpacing(2)
        name = player.name or "Resolving…"
        primary = label(name + ("  ·  YOU" if player.is_self else ""))
        primary.setStyleSheet("font-size: 12px; font-weight: 750; color: #F2F6FA;")
        secondary = label(player.agent or "Not selected", "Hint")
        names.addWidget(primary)
        names.addWidget(secondary)
        horizontal.addLayout(names, 1)
        if player.kd is not None:
            stats = QVBoxLayout()
            stats.setSpacing(2)
            kd = label(f"{player.kd:.2f} K/D")
            kd.setAlignment(Qt.AlignmentFlag.AlignRight)
            kd.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 800;")
            rate = f"{player.winrate:.0%} WR" if player.winrate is not None else "WR n/a"
            bottom = label(f"{rate}  ·  {player.games} games", "Hint")
            bottom.setAlignment(Qt.AlignmentFlag.AlignRight)
            stats.addWidget(kd)
            stats.addWidget(bottom)
            horizontal.addLayout(stats)
        elif show_stats:
            unknown = label("STATS N/A", "Hint")
            horizontal.addWidget(unknown)

    def set_icon(self, pixmap: QPixmap):
        self.icon_label.setPixmap(pixmap.scaled(42, 43, Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation))
        self.icon_label.setText("")


class SettingsDialog(QDialog):
    def __init__(self, parent, current_key: str, auto_refresh: bool, stats_on: bool):
        super().__init__(parent)
        self.setWindowTitle("ValIntel · Settings")
        self.setModal(True)
        self.setMinimumWidth(455)
        self.setStyleSheet(STYLESHEET)
        l = QVBoxLayout(self)
        l.setContentsMargins(26, 26, 26, 26)
        l.setSpacing(15)
        l.addWidget(label("APPLICATION SETTINGS", "Kicker"))
        h = label("Customize your workspace", "SectionTitle")
        l.addWidget(h)
        l.addWidget(label("HenrikDEV API key", "Muted"))
        self.key_field = QLineEdit(current_key)
        self.key_field.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_field.setPlaceholderText("Enter your HenrikDEV API key")
        l.addWidget(self.key_field)
        self.show_key = QCheckBox("Show key")
        self.show_key.toggled.connect(lambda show: self.key_field.setEchoMode(
            QLineEdit.EchoMode.Normal if show else QLineEdit.EchoMode.Password))
        l.addWidget(self.show_key)
        l.addWidget(separator())
        self.refresh_box = QCheckBox(f"Auto-detect matches every {REFRESH_SECONDS} seconds")
        self.refresh_box.setChecked(auto_refresh)
        l.addWidget(self.refresh_box)
        self.stats_box = QCheckBox("Load recent Competitive stats once per match")
        self.stats_box.setChecked(stats_on)
        l.addWidget(self.stats_box)
        tip = label("Your key is saved under this Windows account, not embedded in the EXE.", "Hint", True)
        l.addWidget(tip)
        controls = QHBoxLayout()
        controls.addWidget(button("REMOVE KEY", self.remove_key))
        controls.addStretch()
        controls.addWidget(button("CANCEL", self.reject))
        controls.addWidget(button("SAVE SETTINGS", self.accept, "Primary"))
        l.addLayout(controls)
        self.delete_requested = False

    def remove_key(self):
        self.key_field.clear()
        self.delete_requested = True
        QMessageBox.information(self, "ValIntel", "Key will be deleted when you save settings.")


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
        self.nav_settings = button("⚙   SETTINGS", self.open_settings, "Nav", 45)
        for nav in (self.nav_overview, self.nav_agents, self.nav_teams, self.nav_insights, self.nav_patterns, self.nav_settings):
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
        layout.addWidget(label("UNOFFICIAL CLIENT ENDPOINTS  •   USE AT YOUR OWN RISK", "Hint"))
        self.update_key_indicator()

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


if __name__ == "__main__":
    main()
