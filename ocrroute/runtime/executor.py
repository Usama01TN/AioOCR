"""Execute a single engine attempt off the event loop."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ocrroute.catalog.registry import get_registry
from ocrroute.logutil import get_logger

log = get_logger(__name__)

_pool: ThreadPoolExecutor | None = None


def get_pool(workers: int = 8) -> ThreadPoolExecutor:
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ocrroute")
    return _pool


def _run_engine_sync(
    engine_id: str,
    image: Any,
    *,
    api_list: list[str] | None = None,
    endpoint: str | None = None,
    model: str | None = None,
    language: Any = None,
    timeout: int = 30,
    retries: int = 3,
    proxy: dict | None = None,
    prompt: str | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = get_registry()
    kwargs: dict[str, Any] = {
        "image": image,
        "timeout": timeout,
        "retries": retries,
    }
    if api_list:
        kwargs["apiList"] = api_list
        kwargs["api"] = api_list[0]
    if endpoint:
        kwargs["endpoint"] = endpoint
    if model:
        kwargs["model"] = model
    if language is not None:
        kwargs["language"] = language
    if proxy:
        kwargs["proxy"] = proxy
    if prompt:
        kwargs["prompt"] = prompt
    if options:
        kwargs.update(options)

    instance = registry.create_instance(engine_id, **kwargs)
    return instance.parse()


async def run_engine(
    engine_id: str,
    image: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    pool = get_pool()
    return await loop.run_in_executor(
        pool,
        lambda: _run_engine_sync(engine_id, image, **kwargs),
    )


def sync_execute_candidate(
    candidate: dict[str, Any],
    secrets: list[str],
    credential: dict[str, Any],
    *,
    image: Any,
    language: Any = None,
    prompt: str | None = None,
    extra_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Synchronous executor used by Router.execute_fn."""
    options = dict(candidate.get("options") or {})
    options.update(candidate.get("option_overrides") or {})
    if extra_options:
        options.update(extra_options)
    return _run_engine_sync(
        candidate["engine_id"],
        image,
        api_list=secrets or None,
        endpoint=candidate.get("endpoint"),
        model=candidate.get("model"),
        language=language or candidate.get("language"),
        timeout=int(candidate.get("timeout") or 30),
        retries=int(candidate.get("retries") or 3),
        proxy=candidate.get("proxy"),
        prompt=prompt,
        options=options,
    )
