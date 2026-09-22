"""Render word-box overlay PNG."""
from __future__ import annotations

from io import BytesIO
from typing import Any


def render_overlay(
    image_bytes: bytes,
    result: dict[str, Any],
    *,
    line_color: tuple[int, int, int] = (0, 180, 0),
    word_color: tuple[int, int, int] = (0, 100, 255),
) -> bytes:
    from PIL import Image, ImageDraw

    img = Image.open(BytesIO(image_bytes)).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for line in (result.get("TextOverlay") or {}).get("Lines") or []:
        words = line.get("Words") or []
        if words:
            left = min(w["Left"] for w in words)
            top = min(w["Top"] for w in words)
            right = max(w["Left"] + w["Width"] for w in words)
            bottom = max(w["Top"] + w["Height"] for w in words)
            draw.rectangle([left, top, right, bottom], outline=line_color + (180,), width=2)
        for w in words:
            draw.rectangle(
                [
                    w["Left"],
                    w["Top"],
                    w["Left"] + w["Width"],
                    w["Top"] + w["Height"],
                ],
                outline=word_color + (200,),
                width=1,
            )

    composed = Image.alpha_composite(img, overlay).convert("RGB")
    buf = BytesIO()
    composed.save(buf, format="PNG")
    return buf.getvalue()
