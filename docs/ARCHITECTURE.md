# Architecture

## Layers

```
┌─────────────────────────────────────────────────────────┐
│  CLI (Typer)  ·  Web Panel (Jinja/HTMX)  ·  Desktop (Qt) │
├─────────────────────────────────────────────────────────┤
│  FastAPI  /v1  +  /panel                                 │
├─────────────────────────────────────────────────────────┤
│  Runtime: executor · cache · limits · queue · jobs       │
├─────────────────────────────────────────────────────────┤
│  Routing: strategies · breaker · consensus · cost        │
├─────────────────────────────────────────────────────────┤
│  Pipeline: input (SSRF) · preprocess · postprocess · export │
├─────────────────────────────────────────────────────────┤
│  Catalog: engine registry over vendored AioOCR           │
├─────────────────────────────────────────────────────────┤
│  ocrroute/engines/  ← AioOCR tree (OCRPlugin style)      │
└─────────────────────────────────────────────────────────┘
                              │
                         SQLite WAL
```

## Style boundary

| Layer | Style |
|---|---|
| `ocrroute/engines/` (AioOCR) | Python-2 **and** 3 friendly: `# coding=utf-8`, camelCase methods, `__m_` privates, dual-import shims, `engines/_compat.py` helpers (`string_types`, `ensure_text`, `urlparse`, …) |
| `ocrroute/` gateway | Modern Python 3.10+: snake_case, Pydantic, async SQLAlchemy, type hints |

Gateway code **imports** engines; it does not rewrite them. The legacy
`OcrBase(...).parse(Engine=[{...}])` shape is preserved in `ocrroute.compat.OcrBase`.

## UI internationalisation & themes

- Catalogues live in `ocrroute/i18n/` (`en`, `ar`, `fr`, `de`, `es`, `zh`).
- Panel locale + `dir` (RTL for Arabic) from `?lang=`, session, cookie, or `Accept-Language`.
- Theme: `light` / `dark` / `system` via `data-theme`, CSS variables, and localStorage.
- Desktop loads matching QSS and honours `QSettings` language + layout direction.

## Identity

- Product: **OcrRoute**
- Package: `ocrroute`
- Ports: API **20256**, panel split **20257**
- Never port 20128; never OmniRoute namespaces or chat endpoints
