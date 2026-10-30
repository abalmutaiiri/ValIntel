"""Circular match-estimate widget."""
from __future__ import annotations
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import QWidget, QSizePolicy

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
