"""In-memory sliding-window rate limits and budgets."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Any


class SlidingWindowCounter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, window_seconds: float = 60.0) -> int:
        now = time.monotonic()
        with self._lock:
            q = self._events[key]
            q.append(now)
            cutoff = now - window_seconds
            while q and q[0] < cutoff:
                q.popleft()
            return len(q)

    def count(self, key: str, window_seconds: float = 60.0) -> int:
        now = time.monotonic()
        with self._lock:
            q = self._events[key]
            cutoff = now - window_seconds
            while q and q[0] < cutoff:
                q.popleft()
            return len(q)


class LimitTracker:
    def __init__(self) -> None:
        self.rpm = SlidingWindowCounter()
        self.rpd = SlidingWindowCounter()
        self.spend: dict[str, float] = defaultdict(float)
        self._lock = threading.Lock()

    def check_and_hit(
        self,
        key: str,
        *,
        rpm_limit: int | None = None,
        rpd_limit: int | None = None,
        monthly_budget_cents: float | None = None,
        cost_cents: float = 0.0,
    ) -> tuple[bool, str | None]:
        if rpm_limit is not None:
            n = self.rpm.count(f"rpm:{key}", 60.0)
            if n >= rpm_limit:
                return False, "rpm_limit"
        if rpd_limit is not None:
            n = self.rpd.count(f"rpd:{key}", 86400.0)
            if n >= rpd_limit:
                return False, "rpd_limit"
        if monthly_budget_cents is not None:
            with self._lock:
                if self.spend[key] + cost_cents > monthly_budget_cents:
                    return False, "monthly_budget"
        self.rpm.hit(f"rpm:{key}", 60.0)
        self.rpd.hit(f"rpd:{key}", 86400.0)
        if cost_cents:
            with self._lock:
                self.spend[key] += cost_cents
        return True, None

    def used_rpm(self, key: str) -> int:
        return self.rpm.count(f"rpm:{key}", 60.0)

    def used_rpd(self, key: str) -> int:
        return self.rpd.count(f"rpd:{key}", 86400.0)


_tracker: LimitTracker | None = None


def get_limits() -> LimitTracker:
    global _tracker
    if _tracker is None:
        _tracker = LimitTracker()
    return _tracker
