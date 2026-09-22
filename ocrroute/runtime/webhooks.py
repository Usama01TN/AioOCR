"""Outbound webhook delivery."""
from __future__ import annotations

from typing import Any

import httpx

from ocrroute.logutil import get_logger

log = get_logger(__name__)


async def deliver_webhook(url: str, payload: dict[str, Any], timeout: float = 15.0) -> bool:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return True
    except Exception as exc:
        log.warning("webhook_failed", url=url, error=str(exc))
        return False
