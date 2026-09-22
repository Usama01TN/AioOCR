"""Run first k healthy candidates in parallel (ordering only; execution in router)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ocrroute.routing.strategies.base import Strategy, register


@register("ensemble_vote")
class EnsembleVoteStrategy(Strategy):
    """Orders by quality; router runs top-k concurrently."""

    def order(
        self, candidates: Sequence[dict[str, Any]], context: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        k = int((context or {}).get("ensemble_k", 3))
        ordered = sorted(
            candidates,
            key=lambda c: (
                -float(c.get("quality_score", 0.5) or 0.5),
                c.get("order_index", 0),
            ),
        )
        # Tag for router
        for i, c in enumerate(ordered):
            c = dict(c)
            c["_ensemble"] = i < k
            ordered[i] = c
        return ordered

    def explain(self, context: dict[str, Any] | None = None) -> list[str]:
        k = int((context or {}).get("ensemble_k", 3))
        return ["strategy=ensemble_vote", f"ensemble_k={k}"]
