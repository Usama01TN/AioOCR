"""Strict order_index fallback chain."""
from __future__ import annotations

from typing import Any, Sequence

from ocrroute.routing.strategies.base import Strategy, register


@register("priority")
class PriorityStrategy(Strategy):
    def order(
        self, candidates: Sequence[dict[str, Any]], context: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        return sorted(candidates, key=lambda c: c.get("order_index", 0))
