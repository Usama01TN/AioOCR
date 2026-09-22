"""Bounded in-process concurrency / queue."""
from __future__ import annotations

import asyncio
from typing import Any

from ocrroute.errors import ErrorCode, OcrRouteError


class ConcurrencyGate:
    def __init__(self, global_limit: int = 32, queue_size: int = 256) -> None:
        self.global_sem = asyncio.Semaphore(global_limit)
        self.queue_size = queue_size
        self._waiting = 0
        self._provider_sems: dict[str, asyncio.Semaphore] = {}
        self._in_flight: dict[str, int] = {}
        self._lock = asyncio.Lock()

    def provider_sem(self, provider_id: str, limit: int = 4) -> asyncio.Semaphore:
        if provider_id not in self._provider_sems:
            self._provider_sems[provider_id] = asyncio.Semaphore(limit)
        return self._provider_sems[provider_id]

    async def acquire(self, provider_id: str | None = None, provider_limit: int = 4) -> None:
        async with self._lock:
            if self._waiting >= self.queue_size:
                raise OcrRouteError("Request queue is full", code=ErrorCode.QUEUE_FULL)
            self._waiting += 1
        try:
            await self.global_sem.acquire()
            if provider_id:
                await self.provider_sem(provider_id, provider_limit).acquire()
                self._in_flight[provider_id] = self._in_flight.get(provider_id, 0) + 1
        finally:
            async with self._lock:
                self._waiting = max(0, self._waiting - 1)

    def release(self, provider_id: str | None = None) -> None:
        if provider_id and provider_id in self._provider_sems:
            self._provider_sems[provider_id].release()
            self._in_flight[provider_id] = max(0, self._in_flight.get(provider_id, 0) - 1)
        self.global_sem.release()

    @property
    def waiting(self) -> int:
        return self._waiting

    def in_flight(self, provider_id: str) -> int:
        return self._in_flight.get(provider_id, 0)


_gate: ConcurrencyGate | None = None


def get_gate(global_limit: int = 32, queue_size: int = 256) -> ConcurrencyGate:
    global _gate
    if _gate is None:
        _gate = ConcurrencyGate(global_limit, queue_size)
    return _gate
