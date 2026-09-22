"""Candidate list construction for a Route."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ocrroute.routing.breaker import is_circuit_open
from ocrroute.routing.explain import ExplainLog


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def member_matches_condition(condition: dict[str, Any] | None, ctx: dict[str, Any]) -> bool:
    if not condition:
        return True
    langs = condition.get("language_in") or condition.get("languages")
    if langs:
        req = ctx.get("languages") or []
        if isinstance(req, str):
            req = [req]
        if req and not set(map(str.lower, req)) & set(map(str.lower, langs)):
            return False
    mimes = condition.get("mime_in") or condition.get("mimes")
    if mimes:
        mime = (ctx.get("mime") or "").lower()
        if mime and mime not in [m.lower() for m in mimes]:
            return False
    pages = ctx.get("page_count") or 1
    if "min_pages" in condition and pages < int(condition["min_pages"]):
        return False
    if "max_pages" in condition and pages > int(condition["max_pages"]):
        return False
    max_cost = condition.get("max_cost")
    if max_cost is not None and float(ctx.get("estimated_cost", 0)) > float(max_cost):
        return False
    return True


def build_candidates(
    members: list[dict[str, Any]],
    *,
    context: dict[str, Any] | None = None,
    explain: ExplainLog | None = None,
) -> list[dict[str, Any]]:
    """
    Filter route members into an attemptable candidate list.

    Each member dict should include:
      provider_id, engine_id, kind, enabled, available, order_index, weight,
      circuit_open_until, rpm_limit, rpm_used, rpd_limit, rpd_used,
      monthly_budget_cents, budget_used_cents, condition, ...
    """
    ctx = context or {}
    explain = explain or ExplainLog()
    out: list[dict[str, Any]] = []
    dropped: list[tuple[str, str]] = []

    for m in members:
        label = m.get("label") or m.get("engine_id") or m.get("provider_id") or "?"
        if not m.get("enabled", True):
            dropped.append((label, "disabled"))
            continue
        if not m.get("engine_available", m.get("available", True)):
            dropped.append((label, "engine unavailable"))
            continue
        if is_circuit_open(m):
            dropped.append((label, "circuit open"))
            continue
        rpm = m.get("rpm_limit")
        if rpm is not None and int(m.get("rpm_used") or 0) >= int(rpm):
            dropped.append((label, "rpm limit"))
            continue
        rpd = m.get("rpd_limit")
        if rpd is not None and int(m.get("rpd_used") or 0) >= int(rpd):
            dropped.append((label, "rpd limit"))
            continue
        budget = m.get("monthly_budget_cents")
        if budget is not None and float(m.get("budget_used_cents") or 0) >= float(budget):
            dropped.append((label, "monthly budget"))
            continue
        if not member_matches_condition(m.get("condition"), ctx):
            dropped.append((label, "condition mismatch"))
            continue
        out.append(m)

    for name, reason in dropped:
        explain.add(f"skipped {name} ({reason})")
    return out
