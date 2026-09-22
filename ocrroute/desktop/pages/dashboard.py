from __future__ import annotations

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget


class DashboardPage(QWidget):
    def __init__(self, main=None) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.title = QLabel(self.tr("Dashboard"))
        self.title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(self.title)
        self.stats = QLabel(self.tr("Connect to a server to see KPIs."))
        layout.addWidget(self.stats)
        layout.addStretch()
        self._base = ""

    def set_base_url(self, url: str) -> None:
        self._base = url
        self.stats.setText(self.tr("Server: {}").format(url))
