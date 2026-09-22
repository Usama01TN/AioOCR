# coding=utf-8
"""
Fake OCR engine for tests — never hits live paid APIs.
"""
from __future__ import annotations

from typing import Any

from ocrroute.engines.ocrplugin import OCRPlugin, OCRError


class FakeOcr(OCRPlugin):
    """Deterministic fake engine."""

    # Class-level behaviour knobs for tests
    fail_with: str | None = None
    text: str = "fake text"
    empty: bool = False

    def __init__(self, *args, **kwargs):
        self.__m_minConfidence = kwargs.pop("minConfidence", 0)
        super(FakeOcr, self).__init__(*args, **kwargs)
        self.setOnline(False)

    def _run(self, image, *args, **kwargs):
        if FakeOcr.fail_with:
            msg = FakeOcr.fail_with
            FakeOcr.fail_with = None  # one-shot
            if "auth" in msg.lower() or "401" in msg:
                raise OCRError("Unauthorized: invalid api key")
            if "quota" in msg.lower():
                raise OCRError("quota exceeded")
            if "not an existing file" in msg.lower() or "bad_input" in msg.lower():
                from ocrroute.engines.api.ocrspace import SourceError

                raise SourceError(msg)
            raise OCRError(msg)
        if FakeOcr.empty:
            return []
        return [
            self.makeWord(w, 10.0 + i * 40, 20.0, 35.0, 14.0)
            for i, w in enumerate(FakeOcr.text.split())
        ]


class FakeAuthOcr(OCRPlugin):
    """Fails with auth on first key, succeeds on second via apiList."""

    def __init__(self, *args, **kwargs):
        super(FakeAuthOcr, self).__init__(*args, **kwargs)
        self.setOnline(True)
        self._tried = []

    def _run(self, image, *args, **kwargs):
        key = self.getApi() or (self.getApiList() or [""])[0]
        self._tried.append(key)
        if key == "bad-key":
            raise OCRError("Unauthorized: invalid api key")
        return [self.makeWord("ok", 1, 1, 10, 10)]


def install_fake():
    from ocrroute.catalog.registry import EngineInfo, get_registry

    reg = get_registry()
    reg.discover()
    for cls, kind in ((FakeOcr, "local"), (FakeAuthOcr, "api")):
        info = EngineInfo(
            id=cls.__name__,
            name=cls.__name__,
            kind=kind,
            module="tests.fixtures.fakeocr",
            cls=cls,
            available=True,
            requires_key=(kind == "api"),
            cost_model="local" if kind == "local" else "per_request",
            unit_price=0.0 if kind == "local" else 0.1,
            quality_score=0.9,
            supports_overlay=True,
        )
        reg._engines[cls.__name__] = info
    return FakeOcr
