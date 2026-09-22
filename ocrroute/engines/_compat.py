# coding=utf-8
"""
Python 2 / 3 compatibility helpers for the AioOCR engine layer.

Gateway code (``ocrroute/`` outside ``engines/``) targets Python 3.10+.
Engine modules stay dual-compatible so they can still be imported from
legacy Python-2-era scripts that use the original AioOCR style.
"""
from __future__ import print_function, absolute_import

import sys

PY2 = sys.version_info[0] == 2
PY3 = not PY2

if PY2:  # pragma: no cover - Python 2 only
    text_type = unicode  # noqa: F821
    binary_type = str
    string_types = (basestring,)  # noqa: F821
    integer_types = (int, long)  # noqa: F821
    from urlparse import urlparse  # noqa: F401
    from urllib2 import urlopen  # noqa: F401
    range_type = xrange  # noqa: F821
else:
    text_type = str
    binary_type = bytes
    string_types = (str,)
    integer_types = (int,)
    from urllib.parse import urlparse  # noqa: F401
    from urllib.request import urlopen  # noqa: F401
    range_type = range


def ensure_text(value, encoding="utf-8"):
    """
    Coerce *value* to a unicode/str text object.
    :param value: any
    :param encoding: str
    :return: text_type
    """
    if value is None:
        return u"" if PY2 else ""
    if isinstance(value, text_type):
        return value
    if isinstance(value, binary_type):
        return value.decode(encoding, "replace")
    return text_type(value)


def ensure_binary(value, encoding="utf-8"):
    """
    Coerce *value* to bytes.
    :param value: any
    :param encoding: str
    :return: binary_type
    """
    if value is None:
        return b""
    if isinstance(value, binary_type):
        return value
    if isinstance(value, text_type):
        return value.encode(encoding)
    return text_type(value).encode(encoding)


def iteritems(mapping):
    """dict.items that works on both Python 2 and 3."""
    if hasattr(mapping, "iteritems"):
        return mapping.iteritems()
    return iter(mapping.items())


def itervalues(mapping):
    if hasattr(mapping, "itervalues"):
        return mapping.itervalues()
    return iter(mapping.values())


def iterkeys(mapping):
    if hasattr(mapping, "iterkeys"):
        return mapping.iterkeys()
    return iter(mapping.keys())


def reraise(tp, value, tb=None):
    """Re-raise with traceback (Py2 + Py3)."""
    if PY2:  # pragma: no cover
        exec("raise tp, value, tb")
    else:
        if value is None:
            value = tp()
        if value.__traceback__ is not tb:
            raise value.with_traceback(tb)
        raise value
