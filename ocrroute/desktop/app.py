"""OcrRoute Desktop — PyQt5 client of the /v1 API."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from ocrroute import __version__


def main() -> None:
    try:
        from PyQt5.QtCore import Qt, QThread, pyqtSignal
        from PyQt5.QtGui import QIcon
        from PyQt5.QtWidgets import (
            QApplication,
            QHBoxLayout,
            QLabel,
            QListWidget,
            QListWidgetItem,
            QMainWindow,
            QMessageBox,
            QStackedWidget,
            QSystemTrayIcon,
            QVBoxLayout,
            QWidget,
            QAction,
            QMenu,
        )
    except ImportError as exc:
        print("PyQt5 is required: pip install ocrroute[desktop]", file=sys.stderr)
        raise SystemExit(1) from exc

    # High-DPI
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("OcrRoute Desktop")
    app.setOrganizationName("OcrRoute")
    app.setApplicationVersion(__version__)

    # Theme + layout direction from QSettings / system
    from PyQt5.QtCore import QSettings, QLocale, QTranslator

    qsettings = QSettings()
    theme = str(qsettings.value("ui/theme", "system"))
    lang = str(qsettings.value("ui/language", QLocale.system().name()[:2] or "en"))
    from ocrroute.i18n import AVAILABLE_LOCALES, get_locale

    lang = get_locale(lang)
    meta = AVAILABLE_LOCALES.get(lang, AVAILABLE_LOCALES["en"])
    if meta.get("dir") == "rtl":
        app.setLayoutDirection(Qt.RightToLeft)
    else:
        app.setLayoutDirection(Qt.LeftToRight)

    styles_dir = Path(__file__).resolve().parent / "styles"
    qss_name = "dark.qss"
    if theme == "light":
        qss_name = "light.qss"
    elif theme == "system":
        # Prefer light unless the palette is dark-ish
        try:
            from PyQt5.QtGui import QGuiApplication

            pal = QGuiApplication.palette()
            if pal.color(pal.Window).lightness() >= 128:
                qss_name = "light.qss"
        except Exception:
            qss_name = "light.qss"
    qss_path = styles_dir / qss_name
    if qss_path.is_file():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    # Single-instance lock
    from PyQt5.QtNetwork import QLocalServer, QLocalSocket

    socket = QLocalSocket()
    socket.connectToServer("ocrroute-desktop")
    if socket.waitForConnected(200):
        print("OcrRoute Desktop is already running.", file=sys.stderr)
        sys.exit(0)
    server = QLocalServer()
    QLocalServer.removeServer("ocrroute-desktop")
    server.listen("ocrroute-desktop")

    window = MainWindow()
    window.show()

    # System tray
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = QSystemTrayIcon(window)
        tray.setToolTip("OcrRoute Desktop")
        menu = QMenu()
        menu.addAction("Show", window.showNormal)
        menu.addAction("Quit", app.quit)
        tray.setContextMenu(menu)
        tray.show()
        window._tray = tray

    sys.exit(app.exec_())


class ServerThread(QThread):
    """Embedded Uvicorn in a QThread."""

    ready = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        super().__init__()
        self.host = host
        self.port = port
        self._server = None

    def run(self) -> None:
        import socket

        import uvicorn

        from ocrroute.api.app import create_app

        if self.port == 0:
            with socket.socket() as s:
                s.bind((self.host, 0))
                self.port = s.getsockname()[1]
        try:
            config = uvicorn.Config(
                create_app(),
                host=self.host,
                port=self.port,
                log_level="warning",
            )
            self._server = uvicorn.Server(config)
            self.ready.emit(f"http://{self.host}:{self.port}")
            self._server.run()
        except Exception as exc:
            self.failed.emit(str(exc))

    def stop(self) -> None:
        if self._server:
            self._server.should_exit = True


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        from PyQt5.QtWidgets import (
            QHBoxLayout,
            QLabel,
            QListWidget,
            QListWidgetItem,
            QStackedWidget,
            QVBoxLayout,
            QWidget,
            QAction,
        )

        self.setWindowTitle("OcrRoute Desktop")
        self.resize(1100, 720)
        self._base_url = ""
        self._server_thread: ServerThread | None = None

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)

        self.nav = QListWidget()
        self.nav.setFixedWidth(180)
        pages = [
            "Dashboard",
            "Scan",
            "Batch",
            "Engines",
            "Providers",
            "Routes",
            "History",
            "Tools",
            "Settings",
            "Doctor",
        ]
        for name in pages:
            self.nav.addItem(QListWidgetItem(name))
        layout.addWidget(self.nav)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        from ocrroute.desktop.pages import (
            batch,
            dashboard,
            doctor,
            engines,
            history,
            providers,
            routes,
            scan,
            settings_page,
            tools,
        )

        self._pages = [
            dashboard.DashboardPage(self),
            scan.ScanPage(self),
            batch.BatchPage(self),
            engines.EnginesPage(self),
            providers.ProvidersPage(self),
            routes.RoutesPage(self),
            history.HistoryPage(self),
            tools.ToolsPage(self),
            settings_page.SettingsPage(self),
            doctor.DoctorPage(self),
        ]
        for p in self._pages:
            self.stack.addWidget(p)

        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        # Menu
        file_menu = self.menuBar().addMenu("&File")
        quit_act = QAction("Quit", self)
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        self.statusBar().showMessage("Starting embedded server…")
        self._start_embedded()

    def _start_embedded(self) -> None:
        self._server_thread = ServerThread()
        self._server_thread.ready.connect(self._on_ready)
        self._server_thread.failed.connect(self._on_fail)
        self._server_thread.start()

    def _on_ready(self, url: str) -> None:
        self._base_url = url
        self.statusBar().showMessage(f"Connected: {url}")
        for p in self._pages:
            if hasattr(p, "set_base_url"):
                p.set_base_url(url)

    def _on_fail(self, err: str) -> None:
        from PyQt5.QtWidgets import QMessageBox

        QMessageBox.warning(self, "Server error", err)

    def closeEvent(self, event: Any) -> None:  # noqa: N802
        if self._server_thread:
            self._server_thread.stop()
            self._server_thread.wait(3000)
        event.accept()


if __name__ == "__main__":
    main()
