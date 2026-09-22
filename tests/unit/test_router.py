from __future__ import annotations

import pytest

from ocrroute.errors import ErrorCode, OcrRouteError
from ocrroute.routing.router import Router, is_better, meets_stop_condition, simulate_route


def _ok(text="hello world"):
    return {
        "TextOverlay": {
            "Lines": [
                {
                    "LineText": text,
                    "Words": [
                        {"WordText": w, "Left": i * 10, "Top": 0, "Width": 8, "Height": 10}
                        for i, w in enumerate(text.split())
                    ],
                    "MaxHeight": 10,
                    "MinTop": 0,
                }
            ],
            "HasOverlay": True,
            "Message": "Total lines: 1",
        },
        "TextOrientation": "0",
        "FileParseExitCode": 1,
        "ParsedText": text,
    }


def _err(msg="fail"):
    r = _ok("")
    r["FileParseExitCode"] = -1
    r["ErrorMessage"] = msg
    r["ParsedText"] = ""
    r["TextOverlay"]["Lines"] = []
    return r


def test_fallback_chain():
    calls = []

    def exe(cand, secrets, cred):
        calls.append(cand["engine_id"])
        if cand["engine_id"] == "Bad":
            return _err("Unauthorized: invalid api key")
        return _ok("good")

    members = [
        {
            "provider_id": "1",
            "engine_id": "Bad",
            "label": "bad",
            "kind": "api",
            "enabled": True,
            "engine_available": True,
            "order_index": 0,
            "weight": 1,
            "requires_key": False,
            "credentials": [{"id": "c1", "secret": "x", "enabled": True}],
            "cost_model": "local",
            "unit_price": 0,
        },
        {
            "provider_id": "2",
            "engine_id": "Good",
            "label": "good",
            "kind": "local",
            "enabled": True,
            "engine_available": True,
            "order_index": 1,
            "weight": 1,
            "requires_key": False,
            "credentials": [{"id": None, "secret": "", "enabled": True}],
            "cost_model": "local",
            "unit_price": 0,
        },
    ]
    out = Router(exe).resolve_and_run(members=members, strategy_name="priority", stop_condition={"min_chars": 1})
    assert out["status"] == "succeeded"
    assert out["winning_engine"] == "Good"
    assert out["attempt_count"] == 2
    assert out["attempts"][0]["error_code"] == "auth"


def test_bad_input_fail_fast():
    def exe(cand, secrets, cred):
        return _err("SourceError: not an existing file '/nope'")

    members = [
        {
            "provider_id": "1",
            "engine_id": "X",
            "enabled": True,
            "engine_available": True,
            "order_index": 0,
            "weight": 1,
            "kind": "local",
            "requires_key": False,
            "credentials": [{"secret": ""}],
            "cost_model": "local",
            "unit_price": 0,
        }
    ] * 3
    with pytest.raises(OcrRouteError) as ei:
        Router(exe).resolve_and_run(members=members, strategy_name="priority")
    assert ei.value.code == ErrorCode.BAD_INPUT


def test_credential_rotation():
    tried = []

    def exe(cand, secrets, cred):
        tried.append(cred.get("secret"))
        if cred.get("secret") == "k1":
            return _err("quota exceeded")
        return _ok("rotated")

    members = [
        {
            "provider_id": "p1",
            "engine_id": "E",
            "enabled": True,
            "engine_available": True,
            "order_index": 0,
            "kind": "api",
            "requires_key": True,
            "credentials": [
                {"id": "1", "secret": "k1", "enabled": True},
                {"id": "2", "secret": "k2", "enabled": True},
            ],
            "cost_model": "per_request",
            "unit_price": 0.1,
        }
    ]
    out = Router(exe).resolve_and_run(members=members, strategy_name="priority")
    assert out["status"] == "succeeded"
    assert tried == ["k1", "k2"]


def test_stop_condition():
    assert meets_stop_condition(_ok("abcd"), {"min_chars": 3})
    assert not meets_stop_condition(_ok("ab"), {"min_chars": 3})
    assert not meets_stop_condition(_err(), {"min_chars": 1})


def _member(eid, **kw):
    base = {
        "provider_id": f"p-{eid}",
        "engine_id": eid,
        "label": eid,
        "enabled": True,
        "engine_available": True,
        "order_index": 0,
        "weight": 1,
        "kind": "local",
        "requires_key": False,
        "credentials": [{"id": None, "secret": "", "enabled": True}],
        "cost_model": "local",
        "unit_price": 0,
        "quality_score": 0.7,
    }
    base.update(kw)
    return base


def test_ensemble_vote_mixed_success_and_exception():
    def exe(cand, secrets, cred):
        if cand["engine_id"] == "Flaky":
            raise RuntimeError("boom")
        if cand["engine_id"] == "Bad":
            return _err("parse failed")
        return _ok(f"text from {cand['engine_id']}")

    members = [_member("A"), _member("Flaky"), _member("Bad"), _member("B")]
    out = Router(exe).resolve_and_run(
        members=members, strategy_name="ensemble_vote", context={"ensemble_k": 3}
    )
    assert out["status"] == "succeeded"
    assert out["winning_engine"] == "ensemble"
    assert out["attempt_count"] == 3
    assert any(a["status"] == "failed" for a in out["attempts"])


def test_ensemble_vote_all_failed():
    def exe(cand, secrets, cred):
        raise RuntimeError("always")

    members = [_member("A"), _member("B")]
    out = Router(exe).resolve_and_run(members=members, strategy_name="ensemble_vote")
    assert out["status"] == "failed"
    assert "ensemble_vote" in out["error_message"]


def test_no_candidates_raises():
    with pytest.raises(OcrRouteError) as ei:
        Router(lambda *a: _ok()).resolve_and_run(members=[], strategy_name="priority")
    assert ei.value.code == ErrorCode.NO_CANDIDATE


def test_simulate_route_orders_candidates():
    sim = simulate_route(
        [_member("A", weight=1), _member("B", weight=5)],
        "priority",
        context={},
    )
    assert sim["strategy"] == "priority"
    assert [c["engine"] for c in sim["candidates"]] == ["A", "B"]


def test_is_better_prefers_more_chars():
    # is_better(a, b) is True when b is a better fallback than a
    assert is_better(_ok("a b"), _ok("a b c d"))
    assert not is_better(_ok("a b c"), _ok("a"))
    assert not is_better(_ok("x"), None)
    assert is_better(None, _ok("x"))
    assert is_better(_err(), _ok("x"))
    assert not is_better(_ok("x"), _err())
