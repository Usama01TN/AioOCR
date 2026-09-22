from __future__ import annotations

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget


class BatchPage(QWidget):
    def __init__(self, main=None) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self.tr("Batch")))
        layout.addWidget(QLabel(self.tr("Add files or folders, set concurrency, watch progress.")))
        layout.addStretch()

    def set_base_url(self, url: str) -> None:
        pass
