# Tools (reserved)

This package is a **deliberate placeholder** for future post-processing
extensions. OcrRoute v0.1 ships **no working tools**.

## Contract

Subclass `ToolPlugin` in `ocrroute/tools/builtin/`:

```python
from ocrroute.tools.base import ToolPlugin

class MyTool(ToolPlugin):
    name = "my_tool"
    version = "0.1.0"
    description = "…"
    input_kinds = ["ocr_result"]
    output_kinds = ["ocr_result"]

    def run(self, run_result, **options):
        return run_result
```

The registry auto-discovers subclasses; no gateway code changes are required.

## Ideas only (not commitments)

- Translation of extracted text
- PII redaction
- Table reconstruction
- Spell / layout correction
- Entity extraction
- Document classification
- Summarisation
- Diff against a template
- Barcode / QR reading
- Signature detection
- Language detection

See `docs/TOOLS.md`.
