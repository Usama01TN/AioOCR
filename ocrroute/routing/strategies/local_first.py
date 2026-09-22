"""All local engines before any api engine."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ocrroute.routing.strategies.base import Strategy, register


@register("local_first")
class LocalFirstStrategy(Strategy):
    def order(
        self, candidates: Sequence[dict[str, Any]], context: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        return sorted(
            candidates,
            key=lambda c: (
                0 if c.get("kind") == "local" else 1,
                c.get("order_index", 0),
            ),
        )
