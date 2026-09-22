"""Circuit breaker for providers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def is_circuit_open(provider: dict[str, Any], now: datetime | None = None) -> bool:
    until = provider.get("circuit_open_until")
    if not until:
        return False
    now = now or _utcnow()
    try:
        open_until = datetime.fromisoformat(str(until).replace("Z", "+00:00"))
        if open_until.tzinfo is None:
            open_until = open_until.replace(tzinfo=timezone.utc)
        return open_until > now
    except ValueError:
        return False


def record_success(provider: dict[str, Any]) -> dict[str, Any]:
    provider = dict(provider)
    provider["consecutive_failures"] = 0
    provider["circuit_open_until"] = None
    provider["health"] = "healthy"
    return provider


def record_failure(
    provider: dict[str, Any],
    *,
    threshold: int = 5,
    cooldown_seconds: int = 120,
    now: datetime | None = None,
) -> dict[str, Any]:
    provider = dict(provider)
    fails = int(provider.get("consecutive_failures") or 0) + 1
    provider["consecutive_failures"] = fails
    provider["health"] = "degraded" if fails < threshold else "down"
    if fails >= threshold:
        now = now or _utcnow()
        # Exponential escalation: cooldown * 2^(extra failures beyond threshold)
        extra = fails - threshold
        seconds = cooldown_seconds * (2 ** min(extra, 5))
        until = now + timedelta(seconds=seconds)
        provider["circuit_open_until"] = until.replace(microsecond=0).isoformat()
    return provider


def half_open_allowed(provider: dict[str, Any], now: datetime | None = None) -> bool:
    """True when circuit just expired — allow one probe."""
    until = provider.get("circuit_open_until")
    if not until:
        return False
    now = now or _utcnow()
    try:
        open_until = datetime.fromisoformat(str(until).replace("Z", "+00:00"))
        if open_until.tzinfo is None:
            open_until = open_until.replace(tzinfo=timezone.utc)
        return open_until <= now
    except ValueError:
        return False
