"""Clickable VALORANT agent portrait tile."""
from __future__ import annotations
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel

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
