from __future__ import annotations

import pytest

from ocrroute.errors import ErrorCode, OcrRouteError
from ocrroute.pipeline.input import check_ssrf


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x",
        "http://localhost/x",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.1/x",
        "http://[::1]/x",
    ],
)
def test_blocks_private(url):
    with pytest.raises(OcrRouteError) as ei:
        check_ssrf(url)
    assert ei.value.code == ErrorCode.BAD_INPUT


def test_allowlist():
    # still resolves — may fail DNS in sandbox; allowlist short-circuits after host match
    check_ssrf("https://example.com/a.png", allowlist=["example.com"])


def test_bad_scheme():
    with pytest.raises(OcrRouteError):
        check_ssrf("file:///etc/passwd")
