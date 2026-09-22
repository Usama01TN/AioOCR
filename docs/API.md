# HTTP API

Base path: `/v1`  
OpenAPI: `/v1/openapi.json` · Swagger: `/v1/docs`  
Auth: `Authorization: Bearer ocrr_…`

## OCR

- `POST /v1/ocr` — sync (multipart file **or** JSON `url`/`base64`)
- `POST /v1/ocr/async` — enqueue
- `POST /v1/batch` — job from many items
- `GET /v1/runs/{id}` — envelope
- `GET /v1/runs/{id}/artifacts/{kind}` — export download

## Response envelope

```json
{
  "run_id": "…",
  "status": "succeeded",
  "cached": false,
  "result": { "/* AioOCR unified result verbatim */" },
  "routing": { "route": "…", "strategy": "…", "attempts": [], "explain": [] },
  "usage": { "pages": 1, "chars": 0, "duration_ms": 0, "cost_cents": 0 },
  "artifacts": [],
  "metadata": {}
}
```

Gateway metadata sits **beside** `result`, never inside it.

## Management

Engines, providers, credentials, routes (+ simulate), keys, usage, settings,
audit, tools (reserved), health, ready, version, doctor, `/metrics`.
