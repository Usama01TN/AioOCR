"""OcrRoute internationalisation — catalogues and helpers."""

from __future__ import annotations

from ocrroute.i18n.catalog import (
    AVAILABLE_LOCALES,
    DEFAULT_LOCALE,
    get_locale,
    load_catalog,
    translate,
)

__all__ = [
    "AVAILABLE_LOCALES",
    "DEFAULT_LOCALE",
    "get_locale",
    "load_catalog",
    "translate",
]
