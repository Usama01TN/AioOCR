"""Lowest recent p95 first."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ocrroute.routing.strategies.base import Strategy, register


@register("least_latency")
class LeastLatencyStrategy(Strategy):
    def order(
        self, candidates: Sequence[dict[str, Any]], context: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        return sorted(
            candidates,
            key=lambda c: (
                c.get("p95_ms") if c.get("p95_ms") is not None else 10**9,
                c.get("order_index", 0),
            ),
        )
