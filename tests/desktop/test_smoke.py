"""pytest-qt smoke tests — skipped if PyQt5 missing."""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt5")


def test_tools_page_empty(qtbot):
    from ocrroute.desktop.pages.tools import ToolsPage

    page = ToolsPage()
    qtbot.addWidget(page)
    assert page is not None
    # disabled add button present
    from PyQt5.QtWidgets import QPushButton

    buttons = page.findChildren(QPushButton)
    assert any(not b.isEnabled() for b in buttons)


def test_all_pages_construct(qtbot):
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

    for cls in (
        dashboard.DashboardPage,
        scan.ScanPage,
        batch.BatchPage,
        engines.EnginesPage,
        providers.ProvidersPage,
        routes.RoutesPage,
        history.HistoryPage,
        tools.ToolsPage,
        settings_page.SettingsPage,
        doctor.DoctorPage,
    ):
        w = cls()
        qtbot.addWidget(w)
