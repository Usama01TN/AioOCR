"""Descending curated accuracy score."""
from __future__ import annotations

from typing import Any, Sequence

from ocrroute.routing.strategies.base import Strategy, register


@register("quality_first")
class QualityFirstStrategy(Strategy):
    def order(
        self, candidates: Sequence[dict[str, Any]], context: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        return sorted(
            candidates,
            key=lambda c: (
                -float(c.get("quality_score", 0.5) or 0.5),
                c.get("order_index", 0),
            ),
        )
