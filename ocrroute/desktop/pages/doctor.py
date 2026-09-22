from __future__ import annotations

from PyQt5.QtCore import QThreadPool
from PyQt5.QtWidgets import QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from ocrroute.desktop.workers import FnWorker


class DoctorPage(QWidget):
    def __init__(self, main=None) -> None:
        super().__init__()
        self._base = ""
        self._pool = QThreadPool.globalInstance()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self.tr("Doctor")))
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        layout.addWidget(self.out)
        btn = QPushButton(self.tr("Copy system report"))
        btn.clicked.connect(self._load)
        layout.addWidget(btn)

    def set_base_url(self, url: str) -> None:
        self._base = url
        self._load()

    def _load(self) -> None:
        if not self._base:
            return

        def work():
            from ocrroute.desktop.client import ApiClient

            return ApiClient(self._base).get("/v1/doctor")

        w = FnWorker(work)
        w.signals.finished.connect(lambda d: self.out.setPlainText(str(d)))
        self._pool.start(w)
