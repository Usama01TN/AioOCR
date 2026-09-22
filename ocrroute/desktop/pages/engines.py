from __future__ import annotations

from PyQt5.QtCore import QThreadPool
from PyQt5.QtWidgets import QLabel, QListWidget, QVBoxLayout, QWidget

from ocrroute.desktop.workers import FnWorker


class EnginesPage(QWidget):
    def __init__(self, main=None) -> None:
        super().__init__()
        self._base = ""
        self._pool = QThreadPool.globalInstance()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self.tr("Engines")))
        self.list = QListWidget()
        layout.addWidget(self.list)

    def set_base_url(self, url: str) -> None:
        self._base = url

        def work():
            from ocrroute.desktop.client import ApiClient

            return ApiClient(url).get("/v1/engines")

        w = FnWorker(work)
        w.signals.finished.connect(self._fill)
        self._pool.start(w)

    def _fill(self, data: object) -> None:
        self.list.clear()
        if isinstance(data, dict):
            for e in data.get("engines") or []:
                mark = "✓" if e.get("available") else "✗"
                self.list.addItem(f"{mark} {e.get('id')} ({e.get('kind')})")
