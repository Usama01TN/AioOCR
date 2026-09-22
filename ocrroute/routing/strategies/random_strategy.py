"""Uniform shuffle."""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Any

from ocrroute.routing.strategies.base import Strategy, register


@register("random")
class RandomStrategy(Strategy):
    def order(
        self, candidates: Sequence[dict[str, Any]], context: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        items = list(candidates)
        rng = random.Random((context or {}).get("seed"))
        rng.shuffle(items)
        return items
