# Changelog

## 0.1.0 — 2026-09-22

### Added

- OcrRoute gateway package around vendored AioOCR engines
- FastAPI `/v1` API: OCR, runs, jobs, engines, providers, routes, keys, usage, tools (reserved)
- Routing engine with 14 strategies, breaker, cache, SSRF input pipeline, exports
- Web control panel at `/panel` (Jinja2 + HTMX shell)
- PyQt5 desktop app (`ocrroute desktop`) with embedded server + region capture
- CLI: serve, setup, doctor, engines, ocr, batch, keys, db, …
- SQLite models + bootstrap schema; tools scaffold (§12)
- Docs, Docker files, unit/integration tests with fake engine

### Non-overlap

Stayed clear of OmniRoute scope/naming/ports/assets: OCR-only domain, ports 20256/20257,
glossary Route/Attempt/Engine, pure Python.
