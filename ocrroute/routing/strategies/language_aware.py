"""Providers declaring the request language first."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ocrroute.routing.strategies.base import Strategy, register


@register("language_aware")
class LanguageAwareStrategy(Strategy):
    def order(
        self, candidates: Sequence[dict[str, Any]], context: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        ctx = context or {}
        langs = ctx.get("languages") or []
        if isinstance(langs, str):
            langs = [langs]
        langs_l = {str(x).lower() for x in langs}

        def score(c: dict[str, Any]) -> tuple:
            declared = c.get("languages") or []
            if isinstance(declared, str):
                declared = [declared]
            declared_l = {str(x).lower() for x in declared}
            match = 0 if (not langs_l or declared_l & langs_l or not declared_l) else 1
            # empty declared = universal
            if not declared_l:
                match = 0
            return (match, c.get("order_index", 0))

        return sorted(candidates, key=score)
