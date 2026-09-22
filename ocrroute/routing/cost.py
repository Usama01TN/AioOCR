"""Cost estimation helpers."""
from __future__ import annotations

from typing import Any


def estimate_cost_cents(
    *,
    cost_model: str,
    unit_price: float,
    pages: int = 1,
    chars: int = 0,
    tokens: int = 0,
) -> float:
    """Return estimated cost in cents for one attempt."""
    model = (cost_model or "local").lower()
    price = float(unit_price or 0.0)
    if model in ("free", "local") or price <= 0:
        return 0.0
    if model == "per_page":
        return price * max(1, pages)
    if model == "per_request":
        return price
    if model == "per_token":
        # rough: ~chars/4 tokens if tokens unknown
        t = tokens or max(1, chars // 4)
        return price * (t / 1000.0)
    return price


def starter_prices() -> dict[str, dict[str, Any]]:
    """Bundled starter price table — estimates only, operator-overridable."""
    return {
        "OcrSpace": {"cost_model": "per_request", "unit_price": 0.1},
        "GoogleOcr": {"cost_model": "per_page", "unit_price": 0.15},
        "GeminiOcr": {"cost_model": "per_token", "unit_price": 0.05},
        "ChatGptOcr": {"cost_model": "per_token", "unit_price": 0.08},
        "ClaudeOcr": {"cost_model": "per_token", "unit_price": 0.10},
        "MistralOcr": {"cost_model": "per_page", "unit_price": 0.05},
        "Tesseract": {"cost_model": "local", "unit_price": 0.0},
        "RapidOcr": {"cost_model": "local", "unit_price": 0.0},
        "PaddleOcr": {"cost_model": "local", "unit_price": 0.0},
        "EasyOCR": {"cost_model": "local", "unit_price": 0.0},
    }
