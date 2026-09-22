from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ocrroute.routing.breaker import is_circuit_open, record_failure, record_success


def test_opens_after_threshold():
    p = {"consecutive_failures": 0}
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for _ in range(5):
        p = record_failure(p, threshold=5, cooldown_seconds=120, now=now)
    assert p["consecutive_failures"] == 5
    assert p["circuit_open_until"] is not None
    assert is_circuit_open(p, now=now + timedelta(seconds=10))
    assert not is_circuit_open(p, now=now + timedelta(seconds=200))


def test_success_resets():
    p = record_failure({"consecutive_failures": 3}, threshold=5)
    p = record_success(p)
    assert p["consecutive_failures"] == 0
    assert p["health"] == "healthy"
