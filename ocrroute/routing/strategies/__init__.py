"""Routing strategies registry."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ocrroute.routing.strategies.base import Strategy, get_strategy, list_strategies
from ocrroute.routing.strategies import (  # noqa: F401 — register side effects
    priority,
    round_robin,
    weighted,
    fill_first,
    least_used,
    least_latency,
    p2c,
    random_strategy,
    cost_optimised,
    local_first,
    quality_first,
    language_aware,
    ensemble_vote,
    auto,
)

if TYPE_CHECKING:
    pass

__all__ = ["Strategy", "get_strategy", "list_strategies"]
