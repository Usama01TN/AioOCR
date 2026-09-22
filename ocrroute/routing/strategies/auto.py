"""Heuristic auto strategy — documented in docs/ROUTING.md."""
from __future__ import annotations

from typing import Any, Sequence

from ocrroute.routing.strategies.base import Strategy, get_strategy, register


@register("auto")
class AutoStrategy(Strategy):
    def order(
        self, candidates: Sequence[dict[str, Any]], context: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        ctx = dict(context or {})
        chosen = self._choose(ctx)
        ctx["_auto_chosen"] = chosen
        return get_strategy(chosen).order(candidates, ctx)

    def _choose(self, ctx: dict[str, Any]) -> str:
        if ctx.get("sensitive") or ctx.get("offline"):
            return "local_first"
        if ctx.get("handwriting"):
            return "quality_first"
        if ctx.get("tables") or ctx.get("structured"):
            return "quality_first"
        pages = int(ctx.get("page_count") or 1)
        if pages > 1:
            return "cost_optimised"
        dims = ctx.get("dimensions") or (0, 0)
        w, h = (dims + (0, 0))[:2]
        if w and h and w * h < 1_000_000 and pages == 1:
            return "local_first"
        return "least_latency"

    def explain(self, context: dict[str, Any] | None = None) -> list[str]:
        ctx = dict(context or {})
        chosen = ctx.get("_auto_chosen") or self._choose(ctx)
        reasons = [f"strategy=auto→{chosen}"]
        if ctx.get("sensitive") or ctx.get("offline"):
            reasons.append("reason=sensitive/offline → local_first")
        elif ctx.get("handwriting"):
            reasons.append("reason=handwriting hint → quality_first")
        elif ctx.get("tables") or ctx.get("structured"):
            reasons.append("reason=tables/structured → quality_first")
        elif int(ctx.get("page_count") or 1) > 1:
            reasons.append("reason=multi-page → cost_optimised")
        else:
            reasons.append(f"reason=default heuristic → {chosen}")
        return reasons
