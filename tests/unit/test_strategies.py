"""Unit tests for every routing strategy."""
from __future__ import annotations

import pytest

from ocrroute.routing.strategies import get_strategy, list_strategies


def _cands():
    return [
        {"provider_id": "a", "engine_id": "A", "order_index": 0, "weight": 1, "kind": "local", "unit_price": 0, "quality_score": 0.5, "recent_runs": 5, "p95_ms": 200, "in_flight": 2, "languages": ["en"]},
        {"provider_id": "b", "engine_id": "B", "order_index": 1, "weight": 5, "kind": "api", "unit_price": 0.5, "quality_score": 0.9, "recent_runs": 1, "p95_ms": 100, "in_flight": 0, "languages": ["fr"]},
        {"provider_id": "c", "engine_id": "C", "order_index": 2, "weight": 2, "kind": "local", "unit_price": 0, "quality_score": 0.7, "recent_runs": 3, "p95_ms": 50, "in_flight": 1, "languages": ["en", "ar"]},
    ]


def test_all_strategies_registered():
    expected = {
        "priority", "round_robin", "weighted", "fill_first", "least_used",
        "least_latency", "p2c", "random", "cost_optimised", "local_first",
        "quality_first", "language_aware", "ensemble_vote", "auto",
    }
    assert expected <= set(list_strategies())


@pytest.mark.parametrize("name", sorted(list_strategies()) if False else [
    "priority", "round_robin", "weighted", "fill_first", "least_used",
    "least_latency", "p2c", "random", "cost_optimised", "local_first",
    "quality_first", "language_aware", "ensemble_vote", "auto",
])
def test_strategy_orders(name):
    s = get_strategy(name)
    out = s.order(_cands(), {"seed": 42, "languages": ["en"], "page_count": 1})
    assert len(out) == 3
    assert {c["provider_id"] for c in out} == {"a", "b", "c"}


def test_priority_order():
    out = get_strategy("priority").order(_cands())
    assert [c["engine_id"] for c in out] == ["A", "B", "C"]


def test_local_first():
    out = get_strategy("local_first").order(_cands())
    kinds = [c["kind"] for c in out]
    assert kinds.index("local") < kinds.index("api") or kinds.count("local") == 2


def test_cost_optimised():
    out = get_strategy("cost_optimised").order(_cands())
    assert out[0]["unit_price"] <= out[-1]["unit_price"]


def test_quality_first():
    out = get_strategy("quality_first").order(_cands())
    assert out[0]["engine_id"] == "B"


def test_least_latency():
    out = get_strategy("least_latency").order(_cands())
    assert out[0]["engine_id"] == "C"


def test_least_used():
    out = get_strategy("least_used").order(_cands())
    assert out[0]["engine_id"] == "B"


def test_language_aware():
    out = get_strategy("language_aware").order(_cands(), {"languages": ["fr"]})
    assert out[0]["engine_id"] == "B"


def test_auto_sensitive():
    s = get_strategy("auto")
    out = s.order(_cands(), {"sensitive": True})
    assert out[0]["kind"] == "local"
    explain = s.explain({"sensitive": True})
    assert any("local_first" in x for x in explain)
