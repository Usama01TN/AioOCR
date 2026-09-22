from __future__ import annotations

from ocrroute.pipeline.export import (
    export_alto,
    export_csv,
    export_docx,
    export_hocr,
    export_json,
    export_md,
    export_text,
    write_artifact,
)


def _result():
    return {
        "TextOverlay": {
            "Lines": [
                {
                    "LineText": "Hi",
                    "Words": [{"WordText": "Hi", "Left": 1, "Top": 2, "Width": 10, "Height": 12}],
                    "MaxHeight": 12,
                    "MinTop": 2,
                }
            ],
            "HasOverlay": True,
            "Message": "Total lines: 1",
        },
        "TextOrientation": "0",
        "FileParseExitCode": 1,
        "ParsedText": "Hi",
    }


def test_text():
    assert export_text(_result()) == b"Hi"


def test_json():
    assert b"run_id" in export_json({"run_id": "x", "result": _result()})


def test_md_csv_hocr_alto_docx():
    r = _result()
    assert export_md(r)
    assert b"Hi" in export_csv(r)
    assert b"ocr_line" in export_hocr(r)
    assert b"TextLine" in export_alto(r)
    assert export_docx(r)[:2] == b"PK"


def test_write_artifact():
    env = {"result": _result(), "run_id": "1"}
    assert write_artifact("text", env)
    assert write_artifact("json", env)
