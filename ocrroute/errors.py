"""Error code taxonomy and HTTP status mapping."""
from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    BAD_INPUT = "bad_input"
    UNSUPPORTED_INPUT = "unsupported_input"
    AUTH = "auth"
    QUOTA = "quota"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    NETWORK = "network"
    SERVER_ERROR = "server_error"
    ENGINE_MISSING = "engine_missing"
    EMPTY_RESULT = "empty_result"
    INTERNAL = "internal"
    NO_CANDIDATE = "no_candidate"
    QUEUE_FULL = "queue_full"
    DEADLINE = "deadline"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    FORBIDDEN = "forbidden"
    TOO_LARGE = "too_large"
    UNSUPPORTED_MEDIA = "unsupported_media"
    VALIDATION = "validation"
    INTERRUPTED = "interrupted"
    TOOLS_RESERVED = "tools_reserved"
    CIRCUIT_OPEN = "circuit_open"
    PRIVACY = "privacy"


# Maps error_code → HTTP status
HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.BAD_INPUT: 400,
    ErrorCode.UNSUPPORTED_INPUT: 400,
    ErrorCode.VALIDATION: 422,
    ErrorCode.AUTH: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.CONFLICT: 409,
    ErrorCode.TOO_LARGE: 413,
    ErrorCode.UNSUPPORTED_MEDIA: 415,
    ErrorCode.RATE_LIMIT: 429,
    ErrorCode.QUOTA: 429,
    ErrorCode.SERVER_ERROR: 502,
    ErrorCode.NETWORK: 502,
    ErrorCode.ENGINE_MISSING: 502,
    ErrorCode.EMPTY_RESULT: 502,
    ErrorCode.TIMEOUT: 504,
    ErrorCode.DEADLINE: 504,
    ErrorCode.NO_CANDIDATE: 503,
    ErrorCode.QUEUE_FULL: 503,
    ErrorCode.INTERNAL: 500,
    ErrorCode.INTERRUPTED: 500,
    ErrorCode.TOOLS_RESERVED: 501,
    ErrorCode.CIRCUIT_OPEN: 503,
    ErrorCode.PRIVACY: 403,
}

# Fail-fast codes: do not fan out to other engines
FAIL_FAST = frozenset({ErrorCode.BAD_INPUT, ErrorCode.UNSUPPORTED_INPUT})

# Auth/quota: try next credential on same provider
CREDENTIAL_ROTATE = frozenset({ErrorCode.AUTH, ErrorCode.QUOTA})


class OcrRouteError(Exception):
    """Base application error with machine-readable code."""

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode = ErrorCode.INTERNAL,
        details: dict[str, Any] | None = None,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}
        self.http_status = http_status or HTTP_STATUS.get(code, 500)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.code.value,
            "error_message": self.message,
            "details": self.details,
        }


def classify_exception(exc: BaseException) -> ErrorCode:
    """Map an arbitrary engine exception to an ErrorCode."""
    name = type(exc).__name__
    msg = str(exc).lower()

    if name in ("SourceError",) or "not an existing file" in msg or "unsupported image source" in msg:
        return ErrorCode.BAD_INPUT
    if name in ("FileNotFoundError", "IsADirectoryError"):
        return ErrorCode.BAD_INPUT
    if "unsupported" in msg and ("mime" in msg or "media" in msg or "format" in msg):
        return ErrorCode.UNSUPPORTED_INPUT
    if any(k in msg for k in ("unauthorized", "invalid api key", "invalid key", "401", "forbidden", "authentication")):
        return ErrorCode.AUTH
    if any(k in msg for k in ("quota", "exceeded", "insufficient", "billing", "payment")):
        return ErrorCode.QUOTA
    if any(k in msg for k in ("rate limit", "too many requests", "429", "throttl")):
        return ErrorCode.RATE_LIMIT
    if any(k in msg for k in ("timeout", "timed out", "deadline")):
        return ErrorCode.TIMEOUT
    if any(k in msg for k in ("connection", "network", "dns", "resolve", "refused", "unreachable")):
        return ErrorCode.NETWORK
    if "empty" in msg and "result" in msg:
        return ErrorCode.EMPTY_RESULT
    if name in ("ModuleNotFoundError", "ImportError") or "not installed" in msg:
        return ErrorCode.ENGINE_MISSING
    if any(k in msg for k in ("500", "502", "503", "server error", "internal server")):
        return ErrorCode.SERVER_ERROR
    return ErrorCode.SERVER_ERROR


def http_status_for(code: ErrorCode | str) -> int:
    if isinstance(code, str):
        try:
            code = ErrorCode(code)
        except ValueError:
            return 500
    return HTTP_STATUS.get(code, 500)
