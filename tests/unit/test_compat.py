from __future__ import annotations

from tests.fixtures.fakeocr import FakeOcr, install_fake


def test_legacy_ocrbase_parse():
    install_fake()
    FakeOcr.text = "compat works"
    FakeOcr.fail_with = None
    FakeOcr.empty = False
    from ocrroute.compat import OcrBase

    result = OcrBase().parse(FakeOcr=[{"image": b"not-used"}])
    assert result["FileParseExitCode"] == 1
    assert "compat" in result["ParsedText"]
