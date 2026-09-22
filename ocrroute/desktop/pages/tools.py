from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class ToolsPage(QWidget):
    """Reserved empty Tools page (§12)."""

    def __init__(self, main=None) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        icon = QLabel("🧰")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 48px;")
        layout.addWidget(icon)
        title = QLabel(self.tr("Tools"))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        layout.addWidget(title)
        sub = QLabel(
            self.tr("No tools are installed. This section is reserved for future post-processing extensions.")
        )
        sub.setWordWrap(True)
        sub.setAlignment(Qt.AlignCenter)
        layout.addWidget(sub)
        btn = QPushButton(self.tr("Add tool"))
        btn.setEnabled(False)
        btn.setToolTip(self.tr("Tools are reserved for future use"))
        layout.addWidget(btn, alignment=Qt.AlignCenter)

    def set_base_url(self, url: str) -> None:
        pass
