from __future__ import annotations

from ocrroute.runtime.cache import make_cache_key


def test_stable_key():
    a = make_cache_key("abc", route_or_engine="Tesseract", options={"b": 1, "a": 2})
    b = make_cache_key("abc", route_or_engine="Tesseract", options={"a": 2, "b": 1})
    assert a == b


def test_different_options():
    a = make_cache_key("abc", route_or_engine="Tesseract", options={"x": 1})
    b = make_cache_key("abc", route_or_engine="Tesseract", options={"x": 2})
    assert a != b


def test_different_image():
    a = make_cache_key("abc", route_or_engine="auto")
    b = make_cache_key("def", route_or_engine="auto")
    assert a != b
