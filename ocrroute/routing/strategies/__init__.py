"""Routing strategies registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ocrroute.routing.strategies import (  # noqa: F401 — register side effects
    auto,
    cost_optimised,
    ensemble_vote,
    fill_first,
    language_aware,
    least_latency,
    least_used,
    local_first,
    p2c,
    priority,
    quality_first,
    random_strategy,
    round_robin,
    weighted,
)
from ocrroute.routing.strategies.base import Strategy, get_strategy, list_strategies

if TYPE_CHECKING:
    pass

__all__ = ["Strategy", "get_strategy", "list_strategies"]
