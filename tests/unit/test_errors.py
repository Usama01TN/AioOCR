from __future__ import annotations

from ocrroute.errors import ErrorCode, classify_exception, http_status_for


def test_bad_input():
    assert classify_exception(Exception("not an existing file '/nope'")) == ErrorCode.BAD_INPUT


def test_auth():
    assert classify_exception(Exception("Unauthorized: invalid api key")) == ErrorCode.AUTH


def test_quota():
    assert classify_exception(Exception("quota exceeded")) == ErrorCode.QUOTA


def test_http_map():
    assert http_status_for(ErrorCode.BAD_INPUT) == 400
    assert http_status_for(ErrorCode.RATE_LIMIT) == 429
    assert http_status_for(ErrorCode.NO_CANDIDATE) == 503
    assert http_status_for(ErrorCode.TOOLS_RESERVED) == 501
