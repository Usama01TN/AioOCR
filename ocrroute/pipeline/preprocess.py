"""Optional image preprocessing before engine invocation."""

from __future__ import annotations

from io import BytesIO
from typing import Any


def preprocess_image(
    data: bytes,
    options: dict[str, Any] | None = None,
) -> bytes:
    """
    Apply optional preprocessing. Returns PNG bytes.

    options:
      auto_rotate, grayscale, denoise, contrast, upscale, region [x,y,w,h]
    """
    options = options or {}
    if not any(
        options.get(k)
        for k in ("auto_rotate", "grayscale", "denoise", "contrast", "upscale", "region")
    ):
        return data

    try:
        import numpy as np
        from PIL import Image, ImageFilter, ImageOps
    except ImportError:
        return data

    try:
        img = Image.open(BytesIO(data))
    except Exception:
        return data

    if options.get("region"):
        x, y, w, h = options["region"]
        img = img.crop((int(x), int(y), int(x) + int(w), int(y) + int(h)))

    if (
        options.get("grayscale")
        or options.get("contrast")
        or options.get("denoise")
        or options.get("auto_rotate")
    ):
        gray = img.convert("L")
        if options.get("auto_rotate"):
            arr = np.asarray(gray)
            if arr.mean() < 128:
                gray = ImageOps.invert(gray)
        if options.get("contrast"):
            gray = ImageOps.autocontrast(gray, cutoff=1)
        if options.get("denoise"):
            gray = gray.filter(ImageFilter.MedianFilter(size=3))
        img = gray.convert("RGB") if img.mode != "L" else gray

    if options.get("upscale"):
        longest = max(img.size)
        if longest < 1500:
            factor = min(3, max(2, -(-1500 // longest)))
            img = img.resize((img.width * factor, img.height * factor), Image.LANCZOS)

    if options.get("grayscale") and img.mode != "L":
        img = img.convert("L")

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
