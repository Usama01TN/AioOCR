# coding=utf-8
"""
Vendored AioOCR engines package.

Engine modules use a dual-import shim::

    try:
        from .ocrplugin import OCRPlugin
    except Exception:
        from engines.ocrplugin import OCRPlugin

To keep those shims working when the tree lives under ``ocrroute.engines``,
we put this directory's parent on ``sys.path`` so ``engines.ocrplugin``
resolves here.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ENGINES_PARENT = str(Path(__file__).resolve().parent.parent)
if _ENGINES_PARENT not in sys.path:
    sys.path.insert(0, _ENGINES_PARENT)

# Also expose this package as top-level ``engines`` for legacy imports.
_engines_pkg = sys.modules[__name__]
if "engines" not in sys.modules:
    sys.modules["engines"] = _engines_pkg
if "engines.ocrplugin" not in sys.modules:
    try:
        from ocrroute.engines import ocrplugin as _ocrplugin

        sys.modules["engines.ocrplugin"] = _ocrplugin
    except Exception:
        pass

try:
    from ocrroute.engines.ocrplugin import OCRError, OCRPlugin, is_url
except Exception:  # pragma: no cover
    from engines.ocrplugin import OCRError, OCRPlugin, is_url  # type: ignore

try:
    from ocrroute.engines import _compat as compat
except Exception:  # pragma: no cover
    try:
        import engines._compat as compat  # type: ignore
    except Exception:
        compat = None

__all__ = ["OCRPlugin", "OCRError", "is_url", "compat"]
