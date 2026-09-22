"""Async batch job runner (in-process)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Any

from ocrroute.logutil import get_logger

log = get_logger(__name__)


class JobRunner:
    def __init__(self, concurrency: int = 4) -> None:
        self.concurrency = concurrency
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    def start(self, job_id: str, coro: Awaitable[Any]) -> asyncio.Task[Any]:
        task = asyncio.create_task(coro, name=f"job-{job_id}")
        self._tasks[job_id] = task

        def _done(t: asyncio.Task[Any]) -> None:
            self._tasks.pop(job_id, None)
            if t.cancelled():
                return
            exc = t.exception()
            if exc:
                log.error("job_failed", job_id=job_id, error=str(exc))

        task.add_done_callback(_done)
        return task

    def cancel(self, job_id: str) -> bool:
        t = self._tasks.get(job_id)
        if t and not t.done():
            t.cancel()
            return True
        return False


_runner: JobRunner | None = None


def get_job_runner() -> JobRunner:
    global _runner
    if _runner is None:
        _runner = JobRunner()
    return _runner
