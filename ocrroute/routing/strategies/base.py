"""Strategy base class and registry."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Sequence

_REGISTRY: dict[str, type["Strategy"]] = {}


def register(name: str):
    def deco(cls: type[Strategy]) -> type[Strategy]:
        cls.name = name
        _REGISTRY[name] = cls
        return cls

    return deco


class Strategy(ABC):
    """Pure ordering algorithm over candidate provider dicts."""

    name: str = "base"

    @abstractmethod
    def order(
        self,
        candidates: Sequence[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return candidates in the order they should be attempted."""

    def explain(self, context: dict[str, Any] | None = None) -> list[str]:
        return [f"strategy={self.name}"]


def get_strategy(name: str) -> Strategy:
    cls = _REGISTRY.get(name)
    if cls is None:
        raise KeyError(f"Unknown strategy: {name}. Known: {sorted(_REGISTRY)}")
    return cls()


def list_strategies() -> list[str]:
    return sorted(_REGISTRY)
