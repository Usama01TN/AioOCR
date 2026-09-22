from __future__ import annotations

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget


class SettingsPage(QWidget):
    def __init__(self, main=None) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self.tr("Settings")))
        self.url_label = QLabel("")
        layout.addWidget(self.url_label)
        layout.addStretch()

    def set_base_url(self, url: str) -> None:
        self.url_label.setText(self.tr("Server: {}").format(url))
