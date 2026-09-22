"""Structured logging with secret redaction."""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog

_SECRET_PATTERNS = [
    re.compile(
        r"(?i)(api[_-]?key|apikey|token|secret|password|authorization)\s*[:=]\s*['\"]?([^\s'\",}]+)"
    ),
    re.compile(r"(?i)bearer\s+[a-z0-9\-._~+/]+=*"),
    re.compile(r"ocrr_[A-Za-z0-9]{16,}"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{16,}"),
]


def redact_secrets(value: str) -> str:
    """Scrub likely secrets from a string."""
    if not value:
        return value
    out = value
    for pat in _SECRET_PATTERNS:
        out = pat.sub(
            lambda m: (
                (m.group(0)[: m.end(1) - m.start(0)] + "…[REDACTED]")
                if m.lastindex
                else "…[REDACTED]"
            ),
            out,
        )
        # simpler fallback
        out = pat.sub("…[REDACTED]", out)
    return out


def _redact_processor(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key, val in list(event_dict.items()):
        if isinstance(val, str):
            event_dict[key] = redact_secrets(val)
        elif isinstance(val, dict):
            event_dict[key] = {
                k: redact_secrets(v) if isinstance(v, str) else v for k, v in val.items()
            }
    return event_dict


def setup_logging(level: str = "INFO", json_logs: bool = True) -> None:
    """Configure structlog + stdlib logging."""
    shared = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        _redact_processor,
        structlog.processors.format_exc_info,
    ]
    if json_logs:
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=shared
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Quiet noisy libs
    for name in ("uvicorn.access", "httpx", "httpcore", "aiosqlite"):
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
