from __future__ import annotations

from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from ocrroute.i18n import get_locale, translate


class ToolsPage(QWidget):
    """Reserved empty Tools page (§12)."""

    def __init__(self, main=None) -> None:
        super().__init__()
        lang = get_locale(str(QSettings().value("ui/language", "en")))
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        icon = QLabel("🧰")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 48px;")
        layout.addWidget(icon)
        title = QLabel(translate("tools.title", lang))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        layout.addWidget(title)
        sub = QLabel(translate("tools.empty", lang))
        sub.setWordWrap(True)
        sub.setAlignment(Qt.AlignCenter)
        layout.addWidget(sub)
        btn = QPushButton(translate("tools.add", lang))
        btn.setEnabled(False)
        btn.setToolTip(translate("tools.add_disabled", lang))
        layout.addWidget(btn, alignment=Qt.AlignCenter)

    def set_base_url(self, url: str) -> None:
        pass
