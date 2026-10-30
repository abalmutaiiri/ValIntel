"""One player row in the team roster."""
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QHBoxLayout, QVBoxLayout
from ..models.player import Player
from .widgets import label

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
