"""Random pick proportional to weight (shuffle by weight)."""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Any

from ocrroute.routing.strategies.base import Strategy, register


@register("weighted")
class WeightedStrategy(Strategy):
    def order(
        self, candidates: Sequence[dict[str, Any]], context: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        items = list(candidates)
        # Weighted random shuffle: repeatedly sample without replacement
        result: list[dict[str, Any]] = []
        pool = list(items)
        rng = random.Random((context or {}).get("seed"))
        while pool:
            weights = [max(1, int(c.get("weight", 1))) for c in pool]
            chosen = rng.choices(pool, weights=weights, k=1)[0]
            result.append(chosen)
            pool.remove(chosen)
        return result
