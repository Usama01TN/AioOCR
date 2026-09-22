"""Core routing engine: resolve route, order candidates, execute attempts."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

from ocrroute.errors import ErrorCode, OcrRouteError, classify_exception, FAIL_FAST, CREDENTIAL_ROTATE
from ocrroute.logutil import get_logger, redact_secrets
from ocrroute.routing.candidates import build_candidates
from ocrroute.routing.cost import estimate_cost_cents
from ocrroute.routing.explain import ExplainLog
from ocrroute.routing.strategies import get_strategy
from ocrroute.routing.breaker import record_failure, record_success

log = get_logger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _result_stats(result: dict[str, Any]) -> dict[str, Any]:
    overlay = (result or {}).get("TextOverlay") or {}
    lines = overlay.get("Lines") or []
    words = [w for line in lines for w in (line.get("Words") or [])]
    text = (result or {}).get("ParsedText") or ""
    return {
        "chars": len(text.replace("\r\n", "\n")),
        "lines": len(lines),
        "words": len(words),
        "mean_confidence": None,
        "has_overlay": bool(overlay.get("HasOverlay") and lines),
        "exit_code": (result or {}).get("FileParseExitCode", 1),
    }


def meets_stop_condition(result: dict[str, Any], stop: dict[str, Any] | None) -> bool:
    if (result or {}).get("FileParseExitCode", 1) == -1:
        return False
    stats = _result_stats(result)
    stop = stop or {}
    if stop.get("min_chars") is not None and stats["chars"] < int(stop["min_chars"]):
        return False
    if stop.get("min_mean_confidence") is not None and stats["mean_confidence"] is not None:
        if stats["mean_confidence"] < float(stop["min_mean_confidence"]):
            return False
    if stop.get("require_overlay") and not stats["has_overlay"]:
        return False
    return True


def is_better(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    """Return True if b is a better fallback than a."""
    if b is None:
        return False
    if a is None:
        return True
    sa, sb = _result_stats(a), _result_stats(b)
    if sa["exit_code"] == -1 and sb["exit_code"] != -1:
        return True
    if sb["exit_code"] == -1:
        return False
    return sb["chars"] > sa["chars"]


class Router:
    """
    Executes a Run against an ordered candidate list.

    ``execute_fn(candidate, credential_secrets) -> result_dict`` is injected
    so unit tests can use fakes without real engines.
    """

    def __init__(
        self,
        execute_fn: Callable[..., dict[str, Any]],
        *,
        breaker_threshold: int = 5,
        breaker_cooldown: int = 120,
    ) -> None:
        self.execute_fn = execute_fn
        self.breaker_threshold = breaker_threshold
        self.breaker_cooldown = breaker_cooldown

    def resolve_and_run(
        self,
        *,
        members: list[dict[str, Any]],
        strategy_name: str = "priority",
        context: dict[str, Any] | None = None,
        stop_condition: dict[str, Any] | None = None,
        max_attempts: int = 5,
        total_deadline_ms: int = 120_000,
        credentials_for: Callable[[str], list[dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        explain = ExplainLog()
        ctx = dict(context or {})
        explain.add(f"strategy={strategy_name}")

        candidates = build_candidates(members, context=ctx, explain=explain)
        if not candidates:
            raise OcrRouteError(
                "No candidates available after filtering",
                code=ErrorCode.NO_CANDIDATE,
                details={"explain": explain.as_list()},
            )

        strategy = get_strategy(strategy_name)
        ordered = strategy.order(candidates, ctx)
        explain.extend(strategy.explain(ctx))

        # ensemble_vote: special path
        if strategy_name == "ensemble_vote":
            return self._ensemble(ordered, ctx, explain, stop_condition, credentials_for)

        attempts: list[dict[str, Any]] = []
        best: dict[str, Any] | None = None
        best_attempt_id: str | None = None
        start = time.monotonic()
        deadline = start + (total_deadline_ms / 1000.0)

        for order_idx, cand in enumerate(ordered[:max_attempts]):
            if time.monotonic() > deadline:
                explain.add("deadline exceeded")
                break

            creds = (credentials_for(cand["provider_id"]) if credentials_for else None) or cand.get(
                "credentials"
            ) or [{"id": None, "secret": cand.get("api") or ""}]
            # Filter exhausted
            now_iso = _utcnow_iso()
            usable = [
                c
                for c in creds
                if c.get("enabled", True)
                and (not c.get("exhausted_until") or str(c["exhausted_until"]) <= now_iso)
            ]
            if not usable and cand.get("kind") == "api" and cand.get("requires_key", True):
                attempts.append(
                    {
                        "order": order_idx,
                        "engine": cand.get("engine_id"),
                        "provider": cand.get("label") or cand.get("provider_id"),
                        "status": "skipped",
                        "error_code": ErrorCode.AUTH.value,
                        "duration_ms": 0,
                    }
                )
                explain.add(f"skipped {cand.get('engine_id')} (no credentials)")
                continue
            if not usable:
                usable = [{"id": None, "secret": ""}]

            attempt_result = None
            attempt_meta: dict[str, Any] | None = None
            for ci, cred in enumerate(usable):
                t0 = time.monotonic()
                try:
                    secrets = [c.get("secret", "") for c in usable[ci:]]
                    result = self.execute_fn(cand, secrets, cred)
                    duration = int((time.monotonic() - t0) * 1000)
                    stats = _result_stats(result)
                    if result.get("FileParseExitCode", 1) == -1:
                        err_msg = redact_secrets(
                            str(result.get("ErrorMessage") or result.get("ErrorDetails") or "engine error")
                        )
                        # Build a fake exception for classification
                        code = classify_exception(Exception(err_msg))
                        attempt_meta = {
                            "order": order_idx,
                            "engine": cand.get("engine_id"),
                            "provider": cand.get("label") or cand.get("provider_id"),
                            "credential_id": cred.get("id"),
                            "status": "failed",
                            "error_code": code.value,
                            "error_message": err_msg,
                            "duration_ms": duration,
                            "chars": stats["chars"],
                        }
                        if code in FAIL_FAST:
                            attempts.append(attempt_meta)
                            raise OcrRouteError(err_msg, code=code)
                        if code in CREDENTIAL_ROTATE and ci + 1 < len(usable):
                            explain.add(
                                f"credential rotate on {cand.get('engine_id')} ({code.value})"
                            )
                            continue
                        attempt_result = result
                        break
                    # success
                    attempt_meta = {
                        "order": order_idx,
                        "engine": cand.get("engine_id"),
                        "provider": cand.get("label") or cand.get("provider_id"),
                        "credential_id": cred.get("id"),
                        "status": "succeeded",
                        "duration_ms": duration,
                        "chars": stats["chars"],
                        "cost_cents": estimate_cost_cents(
                            cost_model=cand.get("cost_model", "local"),
                            unit_price=float(cand.get("unit_price") or 0),
                            pages=int(ctx.get("page_count") or 1),
                            chars=stats["chars"],
                        ),
                    }
                    attempt_result = result
                    break
                except OcrRouteError:
                    raise
                except Exception as exc:
                    duration = int((time.monotonic() - t0) * 1000)
                    code = classify_exception(exc)
                    err_msg = redact_secrets(f"{type(exc).__name__}: {exc}")
                    attempt_meta = {
                        "order": order_idx,
                        "engine": cand.get("engine_id"),
                        "provider": cand.get("label") or cand.get("provider_id"),
                        "credential_id": cred.get("id"),
                        "status": "failed",
                        "error_code": code.value,
                        "error_message": err_msg,
                        "duration_ms": duration,
                        "chars": 0,
                    }
                    if code in FAIL_FAST:
                        attempts.append(attempt_meta)
                        raise OcrRouteError(err_msg, code=code)
                    if code in CREDENTIAL_ROTATE and ci + 1 < len(usable):
                        explain.add(f"credential rotate on {cand.get('engine_id')} ({code.value})")
                        continue
                    break

            if attempt_meta:
                attempts.append(attempt_meta)
            if attempt_result is None:
                continue

            if meets_stop_condition(attempt_result, stop_condition):
                explain.add(f"accepted {cand.get('engine_id')}")
                stats = _result_stats(attempt_result)
                return {
                    "result": attempt_result,
                    "status": "succeeded",
                    "degraded": False,
                    "winning_engine": cand.get("engine_id"),
                    "winning_provider": cand.get("label") or cand.get("provider_id"),
                    "winning_provider_id": cand.get("provider_id"),
                    "attempt_count": len(attempts),
                    "attempts": attempts,
                    "explain": explain.as_list(),
                    "stats": stats,
                    "cost_cents": sum(a.get("cost_cents", 0) or 0 for a in attempts),
                    "duration_ms": int((time.monotonic() - start) * 1000),
                }

            if is_better(best, attempt_result):
                best = attempt_result
                best_attempt_id = cand.get("engine_id")
                explain.add(f"kept fallback best from {cand.get('engine_id')}")

        # All candidates exhausted
        if best is not None and _result_stats(best)["exit_code"] != -1 and _result_stats(best)["chars"] > 0:
            stats = _result_stats(best)
            explain.add("returning degraded best result")
            return {
                "result": best,
                "status": "succeeded",
                "degraded": True,
                "winning_engine": best_attempt_id,
                "winning_provider": None,
                "winning_provider_id": None,
                "attempt_count": len(attempts),
                "attempts": attempts,
                "explain": explain.as_list(),
                "stats": stats,
                "cost_cents": sum(a.get("cost_cents", 0) or 0 for a in attempts),
                "duration_ms": int((time.monotonic() - start) * 1000),
            }

        from ocrroute.engines.ocrplugin import OCRPlugin

        err = OCRPlugin.emptyResult()
        err["FileParseExitCode"] = -1
        last_err = next((a for a in reversed(attempts) if a.get("error_message")), None)
        err["ErrorMessage"] = (last_err or {}).get("error_message") or "All candidates failed"
        err["ErrorDetails"] = ""
        code = (last_err or {}).get("error_code") or ErrorCode.SERVER_ERROR.value
        return {
            "result": err,
            "status": "failed",
            "degraded": False,
            "winning_engine": None,
            "winning_provider": None,
            "winning_provider_id": None,
            "attempt_count": len(attempts),
            "attempts": attempts,
            "explain": explain.as_list(),
            "stats": _result_stats(err),
            "cost_cents": sum(a.get("cost_cents", 0) or 0 for a in attempts),
            "duration_ms": int((time.monotonic() - start) * 1000),
            "error_code": code,
            "error_message": err["ErrorMessage"],
        }

    def _ensemble(
        self,
        ordered: list[dict[str, Any]],
        ctx: dict[str, Any],
        explain: ExplainLog,
        stop_condition: dict[str, Any] | None,
        credentials_for: Callable[[str], list[dict[str, Any]]] | None,
    ) -> dict[str, Any]:
        from ocrroute.routing.consensus import reconcile

        k = int(ctx.get("ensemble_k", 3))
        top = ordered[:k]
        explain.add(f"ensemble running k={len(top)}")
        results = []
        attempts = []
        qualities = []
        start = time.monotonic()
        for order_idx, cand in enumerate(top):
            creds = (credentials_for(cand["provider_id"]) if credentials_for else None) or [
                {"id": None, "secret": ""}
            ]
            secrets = [c.get("secret", "") for c in creds]
            t0 = time.monotonic()
            try:
                result = self.execute_fn(cand, secrets, creds[0] if creds else {})
                duration = int((time.monotonic() - t0) * 1000)
                results.append(result)
                qualities.append(float(cand.get("quality_score") or 0.5))
                attempts.append(
                    {
                        "order": order_idx,
                        "engine": cand.get("engine_id"),
                        "provider": cand.get("label") or cand.get("provider_id"),
                        "status": "succeeded"
                        if result.get("FileParseExitCode", 1) != -1
                        else "failed",
                        "duration_ms": duration,
                        "chars": _result_stats(result)["chars"],
                    }
                )
            except Exception as exc:
                duration = int((time.monotonic() - t0) * 1000)
                attempts.append(
                    {
                        "order": order_idx,
                        "engine": cand.get("engine_id"),
                        "status": "failed",
                        "error_code": classify_exception(exc).value,
                        "error_message": redact_secrets(str(exc)),
                        "duration_ms": duration,
                    }
                )
                results.append(None)

        good = [r for r in results if r]
        if not good:
            from ocrroute.engines.ocrplugin import OCRPlugin

            err = OCRPlugin.emptyResult()
            err["FileParseExitCode"] = -1
            err["ErrorMessage"] = "ensemble_vote: all failed"
            return {
                "result": err,
                "status": "failed",
                "degraded": False,
                "attempt_count": len(attempts),
                "attempts": attempts,
                "explain": explain.as_list(),
                "stats": _result_stats(err),
                "cost_cents": 0,
                "duration_ms": int((time.monotonic() - start) * 1000),
                "error_code": ErrorCode.SERVER_ERROR.value,
                "error_message": err["ErrorMessage"],
            }

        consensus, votes = reconcile(
            [r for r in results if r is not None],
            quality_scores=[q for r, q in zip(results, qualities) if r is not None],
        )
        stats = _result_stats(consensus)
        return {
            "result": consensus,
            "status": "succeeded",
            "degraded": False,
            "winning_engine": "ensemble",
            "winning_provider": None,
            "attempt_count": len(attempts),
            "attempts": attempts,
            "explain": explain.as_list(),
            "stats": stats,
            "cost_cents": 0,
            "duration_ms": int((time.monotonic() - start) * 1000),
            "votes": votes,
        }


def simulate_route(
    members: list[dict[str, Any]],
    strategy_name: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Dry-run candidate resolution without executing OCR."""
    explain = ExplainLog()
    ctx = dict(context or {})
    candidates = build_candidates(members, context=ctx, explain=explain)
    strategy = get_strategy(strategy_name)
    ordered = strategy.order(candidates, ctx)
    explain.extend(strategy.explain(ctx))
    return {
        "strategy": strategy_name,
        "candidates": [
            {
                "order": i,
                "engine": c.get("engine_id"),
                "provider": c.get("label") or c.get("provider_id"),
                "kind": c.get("kind"),
                "weight": c.get("weight"),
            }
            for i, c in enumerate(ordered)
        ],
        "explain": explain.as_list(),
    }
