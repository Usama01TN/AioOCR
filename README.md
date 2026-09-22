# OcrRoute

> OcrRoute is an OCR gateway for multi-engine text extraction: one HTTP endpoint in front of
> local and cloud OCR engines, with routing, load balancing, retries and fallbacks — plus
> quotas, caching, cost tracking and observability for reliable, cost-aware document
> understanding.

**OcrRoute is not OmniRoute.** It is an independent Python project. Design patterns for
gateway routing are widely used in the ecosystem; OcrRoute applies them to OCR.

## 60-second quickstart

```bash
pip install -e ".[api,local,dev]"
ocrroute setup          # admin user, default route, API key
ocrroute serve          # http://0.0.0.0:20256  (panel at /panel)
ocrroute ocr ./scan.png # zero-config local OCR when Tesseract is installed
```

- **API port (default):** `20256` — never binds `20128`
- **API base path:** `/v1`
- **Control panel:** `/panel`
- **Data dir:** `~/.ocrroute/` (override with `OCRROUTE_HOME`)

## What it wraps

OcrRoute vendors the **AioOCR** engine tree (`ocrroute/engines/`) as-is: ~22 API engines and
~29 local engines, all returning the same OCR.Space-shaped unified result. Adding an engine
is dropping a module into `engines/api/` or `engines/local/` — no gateway registry edit.

## Features

- Smart **Routes** with 14 strategies (priority, cost_optimised, local_first, ensemble_vote, auto, …)
- Credential rotation, circuit breakers, rate limits, budgets
- Result cache, idempotency, SSRF-safe URL fetch
- Web control panel (Jinja2 + HTMX) and PyQt5 desktop app
- CLI: `ocrroute serve|setup|doctor|ocr|batch|…`
- SQLite only (WAL), Prometheus `/metrics`, OpenAPI at `/v1/docs`

## Install extras

| Extra | Purpose |
|---|---|
| `api` | Core gateway (default deps) |
| `local` | Tesseract / OpenCV helpers |
| `vlm` | torch + transformers for local VLMs |
| `desktop` | PyQt5 desktop app |
| `dev` | pytest, ruff, mypy |
| `all` | Everything |

## Screenshots (placeholders)

1. Panel Overview — KPI cards + live run feed
2. Engines catalogue — availability + install hints
3. Playground — split view with word-box overlay
4. Routes editor — strategy picker + simulate
5. Desktop Scan — region capture → clipboard

## Docs

See `docs/` — ARCHITECTURE, ROUTING, API, ENGINES, DEPLOYMENT, SECURITY, DECISIONS, TOOLS.

## License

MIT
