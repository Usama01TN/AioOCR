from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QThreadPool
from PyQt5.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ocrroute.desktop.workers import FnWorker


class ScanPage(QWidget):
    """Flagship playground page."""

    def __init__(self, main=None) -> None:
        super().__init__()
        self.main = main
        self._base = ""
        self._pool = QThreadPool.globalInstance()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self.tr("Scan")))
        row = QHBoxLayout()
        self.open_btn = QPushButton(self.tr("Open file…"))
        self.open_btn.clicked.connect(self._open)
        self.paste_btn = QPushButton(self.tr("Paste clipboard"))
        self.paste_btn.clicked.connect(self._paste)
        self.region_btn = QPushButton(self.tr("Capture region"))
        self.region_btn.clicked.connect(self._region)
        row.addWidget(self.open_btn)
        row.addWidget(self.paste_btn)
        row.addWidget(self.region_btn)
        layout.addLayout(row)
        self.result = QPlainTextEdit()
        self.result.setReadOnly(True)
        layout.addWidget(self.result)

    def set_base_url(self, url: str) -> None:
        self._base = url

    def _open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Open image"), "", "Images (*.png *.jpg *.jpeg *.tif *.pdf)"
        )
        if path:
            self._run_ocr(path)

    def _paste(self) -> None:
        from PyQt5.QtGui import QGuiApplication
        from PyQt5.QtCore import QStandardPaths
        import tempfile

        clip = QGuiApplication.clipboard()
        img = clip.image()
        if img.isNull():
            self.result.setPlainText(self.tr("Clipboard has no image."))
            return
        tmp = Path(tempfile.gettempdir()) / "ocrroute_clipboard.png"
        img.save(str(tmp), "PNG")
        self._run_ocr(str(tmp))

    def _region(self) -> None:
        """Frameless translucent rubber-band grabber."""
        from PyQt5.QtCore import Qt, QRect, QPoint
        from PyQt5.QtGui import QPainter, QColor, QGuiApplication
        from PyQt5.QtWidgets import QWidget
        import tempfile
        from pathlib import Path

        class Rubber(QWidget):
            def __init__(self, cb):
                super().__init__()
                self.cb = cb
                self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
                self.setWindowState(Qt.WindowFullScreen)
                self.setAttribute(Qt.WA_TranslucentBackground)
                self.origin = QPoint()
                self.current = QRect()
                self.setCursor(Qt.CrossCursor)

            def mousePressEvent(self, e):
                self.origin = e.pos()
                self.current = QRect(self.origin, self.origin)

            def mouseMoveEvent(self, e):
                self.current = QRect(self.origin, e.pos()).normalized()
                self.update()

            def mouseReleaseEvent(self, e):
                self.hide()
                r = self.current
                if r.width() > 2 and r.height() > 2:
                    screen = QGuiApplication.primaryScreen()
                    pix = screen.grabWindow(0, r.x(), r.y(), r.width(), r.height())
                    tmp = Path(tempfile.gettempdir()) / "ocrroute_region.png"
                    pix.save(str(tmp), "PNG")
                    self.cb(str(tmp))
                self.close()

            def paintEvent(self, e):
                p = QPainter(self)
                p.fillRect(self.rect(), QColor(0, 0, 0, 80))
                if not self.current.isNull():
                    p.setCompositionMode(QPainter.CompositionMode_Clear)
                    p.fillRect(self.current, Qt.transparent)
                    p.setCompositionMode(QPainter.CompositionMode_SourceOver)
                    p.setPen(QColor(37, 99, 235))
                    p.drawRect(self.current)

        self._rubber = Rubber(self._run_ocr)
        self._rubber.show()

    def _run_ocr(self, path: str) -> None:
        if not self._base:
            self.result.setPlainText(self.tr("Server not ready."))
            return
        self.result.setPlainText(self.tr("Running…"))
        base = self._base

        def work():
            from ocrroute.desktop.client import ApiClient

            return ApiClient(base).ocr_file(path)

        worker = FnWorker(work)
        worker.signals.finished.connect(self._done)
        worker.signals.error.connect(lambda e: self.result.setPlainText(e))
        self._pool.start(worker)

    def _done(self, env: object) -> None:
        if isinstance(env, dict):
            text = (env.get("result") or {}).get("ParsedText") or ""
            self.result.setPlainText(text)
        else:
            self.result.setPlainText(str(env))
