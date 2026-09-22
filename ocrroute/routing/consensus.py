"""Ensemble vote reconciliation by word-box IoU clustering.

Factored from the clustering idea in engines/local/tesseract.py.
"""
from __future__ import annotations

from typing import Any


def _overlap(a: dict[str, Any], b: dict[str, Any]) -> float:
    x1 = max(float(a.get("Left", 0)), float(b.get("Left", 0)))
    y1 = max(float(a.get("Top", 0)), float(b.get("Top", 0)))
    x2 = min(
        float(a.get("Left", 0)) + float(a.get("Width", 0)),
        float(b.get("Left", 0)) + float(b.get("Width", 0)),
    )
    y2 = min(
        float(a.get("Top", 0)) + float(a.get("Height", 0)),
        float(b.get("Top", 0)) + float(b.get("Height", 0)),
    )
    if x2 <= x1 or y2 <= y1:
        return 0.0
    smaller = min(
        float(a.get("Width", 0)) * float(a.get("Height", 0)),
        float(b.get("Width", 0)) * float(b.get("Height", 0)),
    )
    return (x2 - x1) * (y2 - y1) / max(smaller, 1.0)


def _extract_words(result: dict[str, Any], src: int) -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []
    overlay = (result or {}).get("TextOverlay") or {}
    for line in overlay.get("Lines") or []:
        for w in line.get("Words") or []:
            word = dict(w)
            word["_src"] = src
            word["_conf"] = float(w.get("_conf", w.get("Confidence", 50.0)) or 50.0)
            words.append(word)
    return words


def _cluster(words: list[dict[str, Any]], iou: float = 0.4) -> list[list[dict[str, Any]]]:
    clusters: list[list[dict[str, Any]]] = []
    for word in words:
        hits = [
            i
            for i, cluster in enumerate(clusters)
            if any(_overlap(word, member) >= iou for member in cluster)
        ]
        if not hits:
            clusters.append([word])
        else:
            base = clusters[hits[0]]
            base.append(word)
            for i in reversed(hits[1:]):
                base.extend(clusters[i])
                del clusters[i]
    return clusters


def reconcile(
    results: list[dict[str, Any]],
    *,
    quality_scores: list[float] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Build consensus result from multiple engine results.

    Returns (unified_result, votes_detail).
    """
    from ocrroute.engines.ocrplugin import OCRPlugin

    all_words: list[dict[str, Any]] = []
    for i, res in enumerate(results):
        if not res or res.get("FileParseExitCode", 1) == -1:
            continue
        all_words.extend(_extract_words(res, i))

    if not all_words:
        empty = OCRPlugin.emptyResult()
        empty["FileParseExitCode"] = -1
        empty["ErrorMessage"] = "ensemble_vote: no successful results"
        return empty, {"votes": [], "engines": len(results)}

    clusters = _cluster(all_words)
    final_words: list[dict[str, Any]] = []
    vote_detail: list[dict[str, Any]] = []

    qs = quality_scores or [0.5] * len(results)

    for cluster in clusters:
        # Count text agreement
        counts: dict[str, list[dict[str, Any]]] = {}
        for w in cluster:
            counts.setdefault(w.get("WordText", ""), []).append(w)
        # Pick text agreed by most engines; tie-break mean conf then quality
        best_text = None
        best_score = (-1, -1.0, -1.0)
        for text, members in counts.items():
            n = len({m["_src"] for m in members})
            mean_conf = sum(m["_conf"] for m in members) / len(members)
            q = max(qs[m["_src"]] if m["_src"] < len(qs) else 0.5 for m in members)
            score = (n, mean_conf, q)
            if score > best_score:
                best_score = score
                best_text = text
                best_members = members
        assert best_text is not None
        # Geometry from highest-conf member
        winner = max(best_members, key=lambda m: m["_conf"])
        word = {
            "WordText": best_text,
            "Left": float(winner["Left"]),
            "Top": float(winner["Top"]),
            "Width": float(winner["Width"]),
            "Height": float(winner["Height"]),
        }
        final_words.append(word)
        vote_detail.append(
            {
                "text": best_text,
                "votes": best_score[0],
                "mean_confidence": best_score[1],
                "candidates": list(counts.keys()),
            }
        )

    plugin = OCRPlugin()
    result = plugin.buildResult(final_words)
    return result, {"votes": vote_detail, "engines": len(results), "clusters": len(clusters)}
