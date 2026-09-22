from __future__ import annotations

from ocrroute.i18n import AVAILABLE_LOCALES, get_locale, translate


def test_locales_present():
    assert "en" in AVAILABLE_LOCALES
    assert "ar" in AVAILABLE_LOCALES
    assert AVAILABLE_LOCALES["ar"]["dir"] == "rtl"


def test_translate_fallback():
    assert translate("nav.overview", "en") == "Overview"
    assert translate("nav.overview", "ar")
    assert translate("does.not.exist", "en") == "does.not.exist"


def test_format_kwargs():
    text = translate("engines.subtitle", "en", count=12)
    assert "12" in text


def test_get_locale():
    assert get_locale("ar-TN") == "ar"
    assert get_locale("fr_FR") == "fr"
    assert get_locale("xx") == "en"
