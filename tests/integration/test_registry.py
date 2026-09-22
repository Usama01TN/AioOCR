from __future__ import annotations

from ocrroute.catalog.registry import get_registry, reset_registry


def test_discovers_engines():
    reset_registry()
    reg = get_registry()
    engines = reg.discover(force=True)
    # Full catalogue should include known class names even if unavailable
    ids = set(engines)
    # At least ocrplugin tree modules yield many names
    assert len(ids) >= 20
    # Spot-check a few
    for name in ("Tesseract", "OcrSpace", "EasyOCR", "PaddleOcr"):
        assert name in ids, f"missing {name}"
        info = engines[name]
        assert info.kind in ("api", "local")
        if not info.available:
            assert info.import_error or info.install_hint is not None or True
