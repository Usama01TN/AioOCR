"""Exhaust a provider's remaining quota before moving on."""
from __future__ import annotations

from typing import Any, Sequence

from ocrroute.routing.strategies.base import Strategy, register


@register("fill_first")
class FillFirstStrategy(Strategy):
    def order(
        self, candidates: Sequence[dict[str, Any]], context: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        # Prefer providers with highest remaining quota ratio
        def score(c: dict[str, Any]) -> tuple:
            rpm = c.get("rpm_limit") or 10**9
            used = c.get("rpm_used", 0)
            remaining = max(0, rpm - used)
            return (-remaining, c.get("order_index", 0))

        return sorted(candidates, key=score)
