"""Small reusable widget factories."""
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QFrame, QPushButton, QVBoxLayout

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
