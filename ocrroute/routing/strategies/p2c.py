"""Power-of-two-choices: sample 2, pick fewer in-flight."""
from __future__ import annotations

import random
from typing import Any, Sequence

from ocrroute.routing.strategies.base import Strategy, register


@register("p2c")
class P2CStrategy(Strategy):
    def order(
        self, candidates: Sequence[dict[str, Any]], context: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        items = list(candidates)
        if len(items) <= 2:
            return sorted(items, key=lambda c: c.get("in_flight", 0))
        rng = random.Random((context or {}).get("seed"))
        result: list[dict[str, Any]] = []
        pool = list(items)
        while pool:
            if len(pool) == 1:
                result.append(pool.pop())
                break
            a, b = rng.sample(pool, 2)
            winner = a if a.get("in_flight", 0) <= b.get("in_flight", 0) else b
            result.append(winner)
            pool.remove(winner)
        return result
