"""Post-processing and reserved tools hook."""

from __future__ import annotations

import re
from typing import Any


def normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def filter_low_confidence_words(result: dict[str, Any], min_conf: float) -> dict[str, Any]:
    """Drop words below confidence if present (engine-dependent)."""
    if min_conf <= 0:
        return result
    overlay = result.get("TextOverlay") or {}
    new_lines = []
    for line in overlay.get("Lines") or []:
        words = [
            w
            for w in (line.get("Words") or [])
            if float(w.get("Confidence", w.get("_conf", 100))) >= min_conf
        ]
        if not words:
            continue
        new_lines.append(
            {
                "LineText": " ".join(w["WordText"] for w in words).strip(),
                "Words": words,
                "MaxHeight": max(w["Height"] for w in words),
                "MinTop": min(w["Top"] for w in words),
            }
        )
    result = dict(result)
    result["TextOverlay"] = dict(overlay)
    result["TextOverlay"]["Lines"] = new_lines
    result["TextOverlay"]["Message"] = f"Total lines: {len(new_lines)}"
    result["ParsedText"] = "\r\n".join(line["LineText"] for line in new_lines)
    return result


def apply_postprocess(
    result: dict[str, Any], options: dict[str, Any] | None = None
) -> dict[str, Any]:
    options = options or {}
    if options.get("normalize_whitespace", True) and result.get("ParsedText"):
        result = dict(result)
        # Keep \r\n for OCR.Space compatibility after normalize
        text = normalize_whitespace(result["ParsedText"])
        result["ParsedText"] = text.replace("\n", "\r\n")
    if options.get("min_confidence"):
        result = filter_low_confidence_words(result, float(options["min_confidence"]))
    return result


def apply_tools(result: dict[str, Any], tool_chain: list[Any] | None = None) -> dict[str, Any]:
    """
    Reserved extension point for post-processing tools (§12).

    Today the chain is always empty; this is an identity function.
    Covered by tests asserting identity.
    """
    if not tool_chain:
        return result
    # Future: iterate ToolPlugin.run(...)
    return result
