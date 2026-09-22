from __future__ import annotations

from ocrroute.routing.cost import estimate_cost_cents, starter_prices


def test_local_zero():
    assert estimate_cost_cents(cost_model="local", unit_price=0, pages=10) == 0


def test_per_page():
    assert estimate_cost_cents(cost_model="per_page", unit_price=0.1, pages=3) == pytest.approx(0.3)


def test_per_request():
    assert estimate_cost_cents(cost_model="per_request", unit_price=0.5) == 0.5


def test_starter_table():
    assert "Tesseract" in starter_prices()


import pytest  # noqa: E402
