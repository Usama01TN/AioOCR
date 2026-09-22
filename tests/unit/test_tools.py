from __future__ import annotations

from ocrroute.pipeline.postprocess import apply_tools
from ocrroute.tools.registry import get_tool_registry


def test_registry_empty():
    assert get_tool_registry().list() == []


def test_apply_tools_identity():
    r = {"ParsedText": "x", "FileParseExitCode": 1}
    assert apply_tools(r, None) is r
    assert apply_tools(r, []) is r
