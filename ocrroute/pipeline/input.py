"""Input pipeline: fetch, sniff, SSRF guard, PDF split."""
from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from ocrroute.errors import ErrorCode, OcrRouteError
from ocrroute.logutil import get_logger

log = get_logger(__name__)

# Private / link-local / metadata ranges blocked by default
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

_MIME_BY_MAGIC = [
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"%PDF", "application/pdf"),
    (b"RIFF", "image/webp"),  # rough
    (b"BM", "image/bmp"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
]


@dataclass
class InputDocument:
    """Normalised input ready for engines / preprocessing."""

    data: bytes
    mime: str
    kind: str  # path|url|base64|bytes|pil
    filename: str | None = None
    sha256: str = ""
    page_count: int = 1
    width: int | None = None
    height: int | None = None
    pages: list[bytes] = field(default_factory=list)
    source_url: str | None = None

    def __post_init__(self) -> None:
        if not self.sha256 and self.data:
            self.sha256 = hashlib.sha256(self.data).hexdigest()


def sniff_mime(data: bytes) -> str:
    for magic, mime in _MIME_BY_MAGIC:
        if data.startswith(magic):
            if mime == "image/webp" and b"WEBP" not in data[:16]:
                continue
            return mime
    return "application/octet-stream"


def _host_ips(hostname: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(hostname, None)
        return list({info[4][0] for info in infos})
    except socket.gaierror as exc:
        raise OcrRouteError(
            f"Cannot resolve host: {hostname}",
            code=ErrorCode.BAD_INPUT,
        ) from exc


def check_ssrf(
    url: str,
    *,
    allow_private: bool = False,
    allowlist: list[str] | None = None,
    denylist: list[str] | None = None,
) -> None:
    """Raise if URL targets a blocked address."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise OcrRouteError(
            f"Unsupported URL scheme: {parsed.scheme}",
            code=ErrorCode.BAD_INPUT,
        )
    host = parsed.hostname
    if not host:
        raise OcrRouteError("URL missing host", code=ErrorCode.BAD_INPUT)

    host_l = host.lower()
    if denylist and any(host_l == d.lower() or host_l.endswith("." + d.lower()) for d in denylist):
        raise OcrRouteError(f"Host denied: {host}", code=ErrorCode.BAD_INPUT)
    if allowlist:
        if not any(host_l == a.lower() or host_l.endswith("." + a.lower()) for a in allowlist):
            raise OcrRouteError(f"Host not in allowlist: {host}", code=ErrorCode.BAD_INPUT)
        return

    if allow_private:
        return

    # Block obvious names
    if host_l in ("localhost", "metadata.google.internal"):
        raise OcrRouteError(f"Blocked host: {host}", code=ErrorCode.BAD_INPUT)

    for ip_str in _host_ips(host):
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        for net in _BLOCKED_NETWORKS:
            if ip in net:
                raise OcrRouteError(
                    f"URL resolves to blocked address {ip_str}",
                    code=ErrorCode.BAD_INPUT,
                )


def fetch_url(
    url: str,
    *,
    timeout: int = 30,
    max_bytes: int = 50 * 1024 * 1024,
    allow_private: bool = False,
    allowlist: list[str] | None = None,
    denylist: list[str] | None = None,
    max_redirects: int = 5,
) -> bytes:
    check_ssrf(url, allow_private=allow_private, allowlist=allowlist, denylist=denylist)
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        current = url
        for _ in range(max_redirects + 1):
            check_ssrf(
                current,
                allow_private=allow_private,
                allowlist=allowlist,
                denylist=denylist,
            )
            resp = client.get(current)
            if resp.status_code in (301, 302, 303, 307, 308):
                loc = resp.headers.get("location")
                if not loc:
                    raise OcrRouteError("Redirect without Location", code=ErrorCode.BAD_INPUT)
                current = str(httpx.URL(current).join(loc))
                continue
            resp.raise_for_status()
            data = resp.content
            if len(data) > max_bytes:
                raise OcrRouteError("Download exceeds size limit", code=ErrorCode.TOO_LARGE)
            return data
    raise OcrRouteError("Too many redirects", code=ErrorCode.BAD_INPUT)


def load_base64(text: str) -> bytes:
    import base64

    payload = text.split(",", 1)[-1]
    try:
        return base64.b64decode(payload, validate=False)
    except Exception as exc:
        raise OcrRouteError("Invalid base64 image data", code=ErrorCode.BAD_INPUT) from exc


def parse_page_range(spec: str | None, total: int) -> list[int]:
    """Parse '1-3,7' into 0-based page indices."""
    if not spec or not spec.strip():
        return list(range(total))
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a), int(b)
            for i in range(start, end + 1):
                if 1 <= i <= total:
                    pages.add(i - 1)
        else:
            i = int(part)
            if 1 <= i <= total:
                pages.add(i - 1)
    return sorted(pages) if pages else list(range(total))


def rasterize_pdf(data: bytes, *, dpi: int = 150, pages: str | None = None, max_pages: int = 200) -> list[bytes]:
    """Rasterize PDF pages to PNG bytes. Tries pypdfium2 / PIL fallback."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        # Minimal fallback: treat whole PDF as single opaque blob — engines that
        # accept PDF natively can still use original bytes.
        log.warning("pypdfium2_missing", msg="PDF rasterization unavailable")
        return [data]

    pdf = pdfium.PdfDocument(data)
    total = len(pdf)
    if total > max_pages:
        raise OcrRouteError(
            f"PDF has {total} pages; max is {max_pages}",
            code=ErrorCode.TOO_LARGE,
        )
    indices = parse_page_range(pages, total)
    out: list[bytes] = []
    scale = dpi / 72.0
    for idx in indices:
        page = pdf[idx]
        bitmap = page.render(scale=scale)
        pil = bitmap.to_pil()
        buf = BytesIO()
        pil.save(buf, format="PNG")
        out.append(buf.getvalue())
    return out


def probe_image_size(data: bytes) -> tuple[int | None, int | None]:
    try:
        from PIL import Image

        img = Image.open(BytesIO(data))
        return img.size
    except Exception:
        return None, None


def load_input(
    *,
    path: str | Path | None = None,
    url: str | None = None,
    base64_data: str | None = None,
    raw: bytes | None = None,
    pages: str | None = None,
    pdf_dpi: int = 150,
    max_bytes: int = 50 * 1024 * 1024,
    max_pixels: int = 100_000_000,
    max_pages: int = 200,
    allow_private_urls: bool = False,
    ssrf_allowlist: list[str] | None = None,
    ssrf_denylist: list[str] | None = None,
) -> InputDocument:
    """Load and normalise an OCR input from one of the supported sources."""
    filename = None
    kind = "bytes"
    source_url = None

    if path is not None:
        p = Path(path)
        if not p.is_file():
            raise OcrRouteError(
                f"Image source '{path}' is not an existing file. "
                "Check the path (current working directory matters for relative paths).",
                code=ErrorCode.BAD_INPUT,
            )
        data = p.read_bytes()
        filename = p.name
        kind = "path"
    elif url:
        data = fetch_url(
            url,
            max_bytes=max_bytes,
            allow_private=allow_private_urls,
            allowlist=ssrf_allowlist,
            denylist=ssrf_denylist,
        )
        kind = "url"
        source_url = url
        filename = urlparse(url).path.rsplit("/", 1)[-1] or "download"
    elif base64_data:
        data = load_base64(base64_data)
        kind = "base64"
    elif raw is not None:
        data = raw
        kind = "bytes"
    else:
        raise OcrRouteError("No input provided (file, url, base64, or bytes)", code=ErrorCode.BAD_INPUT)

    if len(data) > max_bytes:
        raise OcrRouteError("Input exceeds size limit", code=ErrorCode.TOO_LARGE)

    mime = sniff_mime(data)
    page_images: list[bytes] = []
    page_count = 1
    width = height = None

    if mime == "application/pdf":
        page_images = rasterize_pdf(data, dpi=pdf_dpi, pages=pages, max_pages=max_pages)
        # If rasterizer returned the raw PDF (no pypdfium2), keep as single page blob
        if len(page_images) == 1 and page_images[0][:4] == b"%PDF":
            page_count = 1
        else:
            page_count = len(page_images)
            if page_images:
                width, height = probe_image_size(page_images[0])
    elif mime.startswith("image/"):
        width, height = probe_image_size(data)
        if width and height and width * height > max_pixels:
            raise OcrRouteError(
                f"Image has {width * height} pixels; max is {max_pixels}",
                code=ErrorCode.TOO_LARGE,
            )
        page_images = [data]
        page_count = 1
        if pages:
            # single image: page range ignored except "1"
            pass
    else:
        raise OcrRouteError(
            f"Unsupported media type: {mime}",
            code=ErrorCode.UNSUPPORTED_MEDIA,
        )

    return InputDocument(
        data=data,
        mime=mime,
        kind=kind,
        filename=filename,
        page_count=page_count,
        width=width,
        height=height,
        pages=page_images,
        source_url=source_url,
    )
