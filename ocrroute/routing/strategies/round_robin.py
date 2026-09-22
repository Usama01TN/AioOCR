"""Rotate start position per Run."""
from __future__ import annotations

from typing import Any, Sequence

from ocrroute.routing.strategies.base import Strategy, register

_counter = 0


@register("round_robin")
class RoundRobinStrategy(Strategy):
    def order(
        self, candidates: Sequence[dict[str, Any]], context: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        global _counter
        items = sorted(candidates, key=lambda c: c.get("order_index", 0))
        if not items:
            return []
        start = _counter % len(items)
        _counter += 1
        return list(items[start:]) + list(items[:start])
