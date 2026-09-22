from __future__ import annotations

from ocrroute.engines._compat import (
    PY3,
    ensure_binary,
    ensure_text,
    iteritems,
    string_types,
)
from ocrroute.engines.ocrplugin import is_url


def test_py3_flags():
    assert PY3 is True


def test_ensure_text_binary():
    assert ensure_text(b"hello") == "hello"
    assert ensure_binary("hello") == b"hello"
    assert isinstance("x", string_types)


def test_iteritems():
    assert dict(iteritems({"a": 1})) == {"a": 1}


def test_is_url_accepts_text():
    assert is_url("https://example.com/a.png")
    assert not is_url("/tmp/x.png")
    assert not is_url(None)
