"""Cheapest estimated cost first (local engines cost 0)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ocrroute.routing.strategies.base import Strategy, register


@register("cost_optimised")
class CostOptimisedStrategy(Strategy):
    def order(
        self, candidates: Sequence[dict[str, Any]], context: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        return sorted(
            candidates,
            key=lambda c: (
                float(c.get("unit_price", 0.0) or 0.0),
                c.get("order_index", 0),
            ),
        )
