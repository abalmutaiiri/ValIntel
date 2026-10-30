"""Settings modal: key management and refresh preferences."""
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QCheckBox, QMessageBox)
from ..config import REFRESH_SECONDS
from .widgets import label, button, separator
from .theme import STYLESHEET

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
