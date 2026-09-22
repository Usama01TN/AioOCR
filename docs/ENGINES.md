# Engines

Engines are `OCRPlugin` subclasses under `ocrroute/engines/{api,local}/`.

Discovery walks both packages, imports each module, and registers subclasses
defined in that module. Import failures are **not** silent: the engine appears
with `available=0`, `import_error`, and an `install_hint`.

Curated metadata lives in `ocrroute/catalog/engines.toml`.

## Unified result

```python
{
  "TextOverlay": {"Lines": [...], "HasOverlay": bool, "Message": "Total lines: N"},
  "TextOrientation": "0",
  "FileParseExitCode": 1,   # -1 on error
  "ParsedText": "line1\r\nline2"
}
```

## Adding an engine

1. Drop `myengine.py` into `engines/api/` or `engines/local/`
2. Subclass `OCRPlugin`, implement `_run(image)` (or override `parse`)
3. Match AioOCR style (`# coding=utf-8`, dual-import shim, camelCase)
4. Restart — no registry or UI edit required
