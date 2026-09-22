"""Fewest Runs in the current window first."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ocrroute.routing.strategies.base import Strategy, register


@register("least_used")
class LeastUsedStrategy(Strategy):
    def order(
        self, candidates: Sequence[dict[str, Any]], context: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        return sorted(
            candidates,
            key=lambda c: (c.get("recent_runs", 0), c.get("order_index", 0)),
        )
