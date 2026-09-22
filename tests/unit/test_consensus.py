from __future__ import annotations

from ocrroute.routing.consensus import reconcile


def _res(words):
    lines = []
    for w in words:
        lines.append(
            {
                "LineText": w["WordText"],
                "Words": [w],
                "MaxHeight": w["Height"],
                "MinTop": w["Top"],
            }
        )
    return {
        "TextOverlay": {"Lines": lines, "HasOverlay": True, "Message": f"Total lines: {len(lines)}"},
        "TextOrientation": "0",
        "FileParseExitCode": 1,
        "ParsedText": "\r\n".join(w["WordText"] for w in words),
    }


def test_vote_agreement():
    w = {"WordText": "Hello", "Left": 10, "Top": 10, "Width": 40, "Height": 12}
    r1 = _res([w])
    r2 = _res([{**w, "WordText": "Hello"}])
    r3 = _res([{**w, "WordText": "Hallo"}])
    result, votes = reconcile([r1, r2, r3], quality_scores=[0.5, 0.5, 0.5])
    assert result["FileParseExitCode"] == 1
    assert "Hello" in result["ParsedText"]
    assert votes["clusters"] >= 1
