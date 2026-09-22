"""Export writers for artifact kinds."""
from __future__ import annotations

import csv
import io
import json
from typing import Any
from xml.sax.saxutils import escape


def export_text(result: dict[str, Any]) -> bytes:
    return ((result or {}).get("ParsedText") or "").encode("utf-8")


def export_json(envelope: dict[str, Any]) -> bytes:
    return json.dumps(envelope, ensure_ascii=False, indent=2).encode("utf-8")


def export_md(result: dict[str, Any]) -> bytes:
    text = (result or {}).get("ParsedText") or ""
    return text.replace("\r\n", "\n").encode("utf-8")


def export_csv(result: dict[str, Any]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["line", "word", "text", "left", "top", "width", "height"])
    for li, line in enumerate((result.get("TextOverlay") or {}).get("Lines") or []):
        for wi, w in enumerate(line.get("Words") or []):
            writer.writerow(
                [
                    li,
                    wi,
                    w.get("WordText", ""),
                    w.get("Left", 0),
                    w.get("Top", 0),
                    w.get("Width", 0),
                    w.get("Height", 0),
                ]
            )
    return buf.getvalue().encode("utf-8")


def export_xlsx(result: dict[str, Any]) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "words"
    ws.append(["line", "word", "text", "left", "top", "width", "height"])
    for li, line in enumerate((result.get("TextOverlay") or {}).get("Lines") or []):
        for wi, w in enumerate(line.get("Words") or []):
            ws.append(
                [
                    li,
                    wi,
                    w.get("WordText", ""),
                    w.get("Left", 0),
                    w.get("Top", 0),
                    w.get("Width", 0),
                    w.get("Height", 0),
                ]
            )
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def export_hocr(result: dict[str, Any], page_width: int = 0, page_height: int = 0) -> bytes:
    lines_xml = []
    for li, line in enumerate((result.get("TextOverlay") or {}).get("Lines") or []):
        words = line.get("Words") or []
        if not words:
            continue
        left = int(min(w["Left"] for w in words))
        top = int(min(w["Top"] for w in words))
        right = int(max(w["Left"] + w["Width"] for w in words))
        bottom = int(max(w["Top"] + w["Height"] for w in words))
        word_parts = []
        for wi, w in enumerate(words):
            bbox = f"{int(w['Left'])} {int(w['Top'])} {int(w['Left']+w['Width'])} {int(w['Top']+w['Height'])}"
            word_parts.append(
                f'<span class="ocrx_word" id="word_{li}_{wi}" title="bbox {bbox}">'
                f"{escape(str(w.get('WordText', '')))}</span>"
            )
        lines_xml.append(
            f'<span class="ocr_line" id="line_{li}" title="bbox {left} {top} {right} {bottom}">'
            + " ".join(word_parts)
            + "</span>"
        )
    body = "\n".join(lines_xml)
    html = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
  "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
<head><title>OcrRoute hOCR</title>
<meta http-equiv="Content-Type" content="text/html;charset=utf-8" />
<meta name="ocr-system" content="OcrRoute" />
</head>
<body>
<div class="ocr_page" id="page_1" title="bbox 0 0 {page_width} {page_height}">
{body}
</div>
</body></html>
"""
    return html.encode("utf-8")


def export_alto(result: dict[str, Any], page_width: int = 0, page_height: int = 0) -> bytes:
    blocks = []
    for li, line in enumerate((result.get("TextOverlay") or {}).get("Lines") or []):
        words = line.get("Words") or []
        strings = []
        for w in words:
            strings.append(
                f'<String CONTENT="{escape(str(w.get("WordText", "")))}" '
                f'HPOS="{int(w["Left"])}" VPOS="{int(w["Top"])}" '
                f'WIDTH="{int(w["Width"])}" HEIGHT="{int(w["Height"])}" />'
            )
        if not words:
            continue
        left = int(min(w["Left"] for w in words))
        top = int(min(w["Top"] for w in words))
        width = int(max(w["Left"] + w["Width"] for w in words) - left)
        height = int(max(w["Top"] + w["Height"] for w in words) - top)
        blocks.append(
            f'<TextLine ID="line_{li}" HPOS="{left}" VPOS="{top}" WIDTH="{width}" HEIGHT="{height}">'
            + "".join(strings)
            + "</TextLine>"
        )
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v3#">
  <Layout>
    <Page ID="page_1" WIDTH="{page_width}" HEIGHT="{page_height}">
      <PrintSpace>
        <TextBlock ID="block_0">
          {"".join(blocks)}
        </TextBlock>
      </PrintSpace>
    </Page>
  </Layout>
</alto>
"""
    return xml.encode("utf-8")


def export_docx(result: dict[str, Any]) -> bytes:
    """Minimal docx writer without python-docx dependency (ZIP+XML)."""
    import zipfile

    text = ((result or {}).get("ParsedText") or "").replace("\r\n", "\n")
    paragraphs = "".join(
        f"<w:p><w:r><w:t xml:space=\"preserve\">{escape(line)}</w:t></w:r></w:p>"
        for line in text.split("\n")
    )
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>{paragraphs}<w:sectPr/></w:body>
</w:document>"""
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document_xml)
    return bio.getvalue()


def export_searchable_pdf(image_bytes: bytes, result: dict[str, Any]) -> bytes:
    """Searchable PDF: raster page + invisible text positioned from word boxes."""
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow required for PDF export") from exc

    # Prefer reportlab if available; else minimal PDF
    try:
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas

        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        bio = io.BytesIO()
        c = canvas.Canvas(bio, pagesize=(w, h))
        c.drawImage(ImageReader(img), 0, 0, width=w, height=h)
        c.setFillColorRGB(0, 0, 0, alpha=0)
        for line in (result.get("TextOverlay") or {}).get("Lines") or []:
            for word in line.get("Words") or []:
                text = str(word.get("WordText") or "")
                if not text:
                    continue
                x = float(word["Left"])
                # PDF y is bottom-up
                y = h - float(word["Top"]) - float(word["Height"])
                font_size = max(6, float(word["Height"]) * 0.9)
                c.setFont("Helvetica", font_size)
                c.drawString(x, y, text)
        c.showPage()
        c.save()
        return bio.getvalue()
    except ImportError:
        pass

    # Fallback: image-only PDF via Pillow
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    bio = io.BytesIO()
    img.save(bio, format="PDF")
    return bio.getvalue()


WRITERS = {
    "text": lambda env, **kw: export_text(env.get("result") or env),
    "json": lambda env, **kw: export_json(env),
    "md": lambda env, **kw: export_md(env.get("result") or env),
    "csv": lambda env, **kw: export_csv(env.get("result") or env),
    "xlsx": lambda env, **kw: export_xlsx(env.get("result") or env),
    "hocr": lambda env, **kw: export_hocr(
        env.get("result") or env, kw.get("width", 0), kw.get("height", 0)
    ),
    "alto": lambda env, **kw: export_alto(
        env.get("result") or env, kw.get("width", 0), kw.get("height", 0)
    ),
    "docx": lambda env, **kw: export_docx(env.get("result") or env),
}


def write_artifact(
    kind: str,
    envelope_or_result: dict[str, Any],
    *,
    image_bytes: bytes | None = None,
    width: int = 0,
    height: int = 0,
) -> bytes:
    kind = kind.lower()
    if kind == "pdf":
        result = envelope_or_result.get("result") or envelope_or_result
        if not image_bytes:
            raise ValueError("pdf export requires image_bytes")
        return export_searchable_pdf(image_bytes, result)
    if kind == "overlay_png":
        from ocrroute.pipeline.overlay import render_overlay

        result = envelope_or_result.get("result") or envelope_or_result
        if not image_bytes:
            raise ValueError("overlay_png requires image_bytes")
        return render_overlay(image_bytes, result)
    writer = WRITERS.get(kind)
    if not writer:
        raise ValueError(f"Unknown artifact kind: {kind}")
    return writer(envelope_or_result, width=width, height=height)
