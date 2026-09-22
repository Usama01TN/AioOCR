from __future__ import annotations

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget


class ProvidersPage(QWidget):
    def __init__(self, main=None) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self.tr("Providers & Credentials")))
        layout.addWidget(QLabel(self.tr("Manage providers via the API or web panel.")))
        layout.addStretch()

    def set_base_url(self, url: str) -> None:
        pass
