"""High-level OCR service orchestrating pipeline + routing + persistence."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ocrroute.catalog.registry import get_registry
from ocrroute.config import Settings, get_settings
from ocrroute.crypto import SecretBox, new_ulid
from ocrroute.db.models import (
    Attempt,
    Artifact,
    Credential,
    Engine,
    Provider,
    Route,
    RouteMember,
    Run,
)
from ocrroute.errors import ErrorCode, OcrRouteError
from ocrroute.logutil import get_logger, redact_secrets
from ocrroute.pipeline.input import InputDocument, load_input
from ocrroute.pipeline.postprocess import apply_postprocess, apply_tools
from ocrroute.pipeline.preprocess import preprocess_image
from ocrroute.pipeline.export import write_artifact
from ocrroute.routing.router import Router, simulate_route
from ocrroute.runtime.cache import cache_get, cache_put, make_cache_key
from ocrroute.runtime.executor import sync_execute_candidate
from ocrroute.runtime.limits import get_limits

log = get_logger(__name__)


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_envelope(
    *,
    run_id: str,
    status: str,
    result: dict[str, Any],
    routing: dict[str, Any],
    usage: dict[str, Any],
    artifacts: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
    cached: bool = False,
    error_code: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    env: dict[str, Any] = {
        "run_id": run_id,
        "status": status,
        "cached": cached,
        "result": result,
        "routing": routing,
        "usage": usage,
        "artifacts": artifacts or [],
        "metadata": metadata or {},
    }
    if error_code:
        env["error_code"] = error_code
        env["error_message"] = error_message
    return env


class OcrService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.box = SecretBox(settings=self.settings)

    async def ensure_engines_synced(self, session: AsyncSession) -> None:
        registry = get_registry()
        registry.discover()
        now = _utcnow()
        for info in registry.list():
            row = await session.get(Engine, info.id)
            if row is None:
                session.add(
                    Engine(
                        id=info.id,
                        name=info.name,
                        kind=info.kind,
                        vendor=info.vendor,
                        module=info.module,
                        available=1 if info.available else 0,
                        import_error=info.import_error,
                        install_hint=info.install_hint,
                        requires_key=info.requires_key,
                        supports_pdf=info.supports_pdf,
                        supports_handwriting=info.supports_handwriting,
                        supports_tables=info.supports_tables,
                        supports_overlay=info.supports_overlay,
                        languages=info.languages,
                        option_schema=info.option_schema,
                        cost_model=info.cost_model,
                        unit_price=info.unit_price,
                        homepage=info.homepage,
                        docs_url=info.docs_url,
                        quality_score=info.quality_score,
                        first_seen=now,
                        last_seen=now,
                    )
                )
            else:
                row.available = 1 if info.available else 0
                row.import_error = info.import_error
                row.install_hint = info.install_hint
                row.option_schema = info.option_schema
                row.last_seen = now
                row.module = info.module
        await session.flush()

    async def _load_route_members(
        self, session: AsyncSession, route: Route
    ) -> list[dict[str, Any]]:
        result = await session.execute(
            select(RouteMember)
            .where(RouteMember.route_id == route.id, RouteMember.enabled.is_(True))
            .options(selectinload(RouteMember.provider).selectinload(Provider.engine))
            .order_by(RouteMember.order_index)
        )
        members = []
        limits = get_limits()
        for m in result.scalars().all():
            p = m.provider
            if p is None:
                continue
            eng = p.engine
            members.append(
                {
                    "provider_id": p.id,
                    "engine_id": p.engine_id,
                    "label": p.label,
                    "kind": eng.kind if eng else "api",
                    "enabled": p.enabled and m.enabled,
                    "engine_available": bool(eng.available) if eng else False,
                    "available": bool(eng.available) if eng else False,
                    "order_index": m.order_index,
                    "weight": m.weight or p.weight or 1,
                    "timeout": p.timeout,
                    "retries": p.retries,
                    "endpoint": p.endpoint,
                    "model": p.model,
                    "language": p.language,
                    "options": p.options or {},
                    "option_overrides": m.option_overrides or {},
                    "proxy": p.proxy,
                    "condition": m.condition,
                    "circuit_open_until": p.circuit_open_until,
                    "consecutive_failures": p.consecutive_failures,
                    "rpm_limit": p.rpm_limit,
                    "rpm_used": limits.used_rpm(f"prov:{p.id}"),
                    "rpd_limit": p.rpd_limit,
                    "rpd_used": limits.used_rpd(f"prov:{p.id}"),
                    "monthly_budget_cents": p.monthly_budget_cents,
                    "budget_used_cents": 0,
                    "cost_model": eng.cost_model if eng else "per_request",
                    "unit_price": eng.unit_price if eng else 0.0,
                    "quality_score": eng.quality_score if eng else 0.5,
                    "requires_key": eng.requires_key if eng else True,
                    "languages": eng.languages if eng else [],
                    "supports_handwriting": eng.supports_handwriting if eng else False,
                    "supports_tables": eng.supports_tables if eng else False,
                    "supports_pdf": eng.supports_pdf if eng else False,
                }
            )
        return members

    async def _credentials_for(self, session: AsyncSession, provider_id: str) -> list[dict[str, Any]]:
        rows = (
            await session.execute(
                select(Credential)
                .where(Credential.provider_id == provider_id, Credential.enabled.is_(True))
                .order_by(Credential.order_index)
            )
        ).scalars().all()
        out = []
        for c in rows:
            try:
                secret = self.box.decrypt(c.secret_enc)
            except Exception:
                continue
            out.append(
                {
                    "id": c.id,
                    "secret": secret,
                    "enabled": c.enabled,
                    "exhausted_until": c.exhausted_until,
                }
            )
        return out

    async def _resolve_members(
        self,
        session: AsyncSession,
        *,
        engine: str | None,
        provider_id: str | None,
        route_name: str | None,
        api_key_route_id: str | None,
    ) -> tuple[list[dict[str, Any]], str, str | None, dict | None]:
        """Return (members, strategy, route_id, stop_condition)."""
        if engine:
            eng = await session.get(Engine, engine)
            if eng is None:
                # try registry
                info = get_registry().get(engine)
                if info is None:
                    raise OcrRouteError(f"Unknown engine: {engine}", code=ErrorCode.NOT_FOUND)
                await self.ensure_engines_synced(session)
                eng = await session.get(Engine, engine)
            members = [
                {
                    "provider_id": provider_id or f"ad-hoc:{engine}",
                    "engine_id": engine,
                    "label": engine,
                    "kind": eng.kind if eng else "local",
                    "enabled": True,
                    "engine_available": bool(eng.available) if eng else get_registry().get(engine) is not None,
                    "available": True,
                    "order_index": 0,
                    "weight": 1,
                    "timeout": 30,
                    "retries": 3,
                    "endpoint": None,
                    "model": None,
                    "language": None,
                    "options": {},
                    "option_overrides": {},
                    "proxy": None,
                    "condition": None,
                    "circuit_open_until": None,
                    "cost_model": eng.cost_model if eng else "local",
                    "unit_price": eng.unit_price if eng else 0.0,
                    "quality_score": eng.quality_score if eng else 0.5,
                    "requires_key": eng.requires_key if eng else False,
                    "languages": eng.languages if eng else [],
                }
            ]
            if provider_id:
                p = await session.get(Provider, provider_id)
                if p:
                    members[0].update(
                        {
                            "provider_id": p.id,
                            "label": p.label,
                            "endpoint": p.endpoint,
                            "model": p.model,
                            "language": p.language,
                            "timeout": p.timeout,
                            "retries": p.retries,
                            "options": p.options or {},
                            "proxy": p.proxy,
                            "circuit_open_until": p.circuit_open_until,
                        }
                    )
            return members, "priority", None, None

        route: Route | None = None
        if route_name:
            route = (
                await session.execute(select(Route).where(Route.name == route_name))
            ).scalar_one_or_none()
            if route is None:
                route = await session.get(Route, route_name)
            if route is None:
                raise OcrRouteError(f"Unknown route: {route_name}", code=ErrorCode.NOT_FOUND)
        elif api_key_route_id:
            route = await session.get(Route, api_key_route_id)
        if route is None:
            route = (
                await session.execute(
                    select(Route).where(Route.is_default.is_(True), Route.enabled.is_(True))
                )
            ).scalar_one_or_none()

        if route is None:
            # Built-in auto: all available local engines + enabled providers
            return await self._auto_members(session), "auto", None, {"min_chars": 1}

        members = await self._load_route_members(session, route)
        return members, route.strategy, route.id, route.stop_condition

    async def _auto_members(self, session: AsyncSession) -> list[dict[str, Any]]:
        await self.ensure_engines_synced(session)
        engines = (
            await session.execute(
                select(Engine).where(Engine.available == 1, Engine.enabled.is_(True))
            )
        ).scalars().all()
        # Prefer local first in member order; strategy auto will refine
        locals_ = [e for e in engines if e.kind == "local"]
        apis = [e for e in engines if e.kind == "api"]
        ordered = locals_ + apis
        members = []
        for i, eng in enumerate(ordered):
            # Prefer configured providers
            provs = (
                await session.execute(
                    select(Provider).where(
                        Provider.engine_id == eng.id, Provider.enabled.is_(True)
                    )
                )
            ).scalars().all()
            if provs:
                for j, p in enumerate(provs):
                    members.append(
                        {
                            "provider_id": p.id,
                            "engine_id": eng.id,
                            "label": p.label,
                            "kind": eng.kind,
                            "enabled": True,
                            "engine_available": True,
                            "available": True,
                            "order_index": i * 10 + j,
                            "weight": p.weight or 1,
                            "timeout": p.timeout,
                            "retries": p.retries,
                            "endpoint": p.endpoint,
                            "model": p.model,
                            "language": p.language,
                            "options": p.options or {},
                            "option_overrides": {},
                            "proxy": p.proxy,
                            "condition": None,
                            "circuit_open_until": p.circuit_open_until,
                            "cost_model": eng.cost_model,
                            "unit_price": eng.unit_price,
                            "quality_score": eng.quality_score,
                            "requires_key": eng.requires_key,
                            "languages": eng.languages or [],
                            "supports_handwriting": eng.supports_handwriting,
                            "supports_tables": eng.supports_tables,
                            "supports_pdf": eng.supports_pdf,
                        }
                    )
            elif eng.kind == "local":
                members.append(
                    {
                        "provider_id": f"auto:{eng.id}",
                        "engine_id": eng.id,
                        "label": eng.name,
                        "kind": eng.kind,
                        "enabled": True,
                        "engine_available": True,
                        "available": True,
                        "order_index": i * 10,
                        "weight": 1,
                        "timeout": 30,
                        "retries": 2,
                        "endpoint": None,
                        "model": None,
                        "language": None,
                        "options": {},
                        "option_overrides": {},
                        "proxy": None,
                        "condition": None,
                        "circuit_open_until": None,
                        "cost_model": eng.cost_model,
                        "unit_price": eng.unit_price,
                        "quality_score": eng.quality_score,
                        "requires_key": False,
                        "languages": eng.languages or [],
                        "supports_handwriting": eng.supports_handwriting,
                        "supports_tables": eng.supports_tables,
                        "supports_pdf": eng.supports_pdf,
                    }
                )
        return members

    async def run_ocr(
        self,
        session: AsyncSession,
        *,
        doc: InputDocument | None = None,
        path: str | None = None,
        url: str | None = None,
        base64_data: str | None = None,
        raw: bytes | None = None,
        route: str | None = None,
        engine: str | None = None,
        provider_id: str | None = None,
        language: Any = None,
        pages: str | None = None,
        prompt: str | None = None,
        options: dict[str, Any] | None = None,
        preprocess: dict[str, Any] | None = None,
        output: list[str] | None = None,
        stop_condition: dict[str, Any] | None = None,
        cache: bool = True,
        metadata: dict[str, Any] | None = None,
        api_key_id: str | None = None,
        api_key_route_id: str | None = None,
        client_ip: str | None = None,
        user_agent: str | None = None,
        idempotency_key: str | None = None,
        no_cache_header: bool = False,
    ) -> dict[str, Any]:
        if engine and route:
            raise OcrRouteError(
                "engine and route are mutually exclusive",
                code=ErrorCode.VALIDATION,
            )

        settings = self.settings
        if doc is None:
            allowlist = [x for x in settings.ssrf_allowlist.split(",") if x.strip()] or None
            denylist = [x for x in settings.ssrf_denylist.split(",") if x.strip()] or None
            doc = load_input(
                path=path,
                url=url,
                base64_data=base64_data,
                raw=raw,
                pages=pages,
                pdf_dpi=int((options or {}).get("pdfDpi") or 150),
                max_bytes=settings.max_upload_bytes,
                max_pixels=settings.max_pixels,
                max_pages=settings.max_pages,
                allow_private_urls=settings.allow_private_urls,
                ssrf_allowlist=allowlist,
                ssrf_denylist=denylist,
            )

        run_id = new_ulid()
        members, strategy, route_id, route_stop = await self._resolve_members(
            session,
            engine=engine,
            provider_id=provider_id,
            route_name=route,
            api_key_route_id=api_key_route_id,
        )
        stop = stop_condition or route_stop or {"min_chars": 1}

        # Cache
        use_cache = cache and settings.cache_enabled and not no_cache_header and not settings.privacy_mode
        cache_target = engine or route or "auto"
        cache_key = make_cache_key(
            doc.sha256,
            route_or_engine=cache_target,
            options={"language": language, "options": options, "pages": pages, "prompt": prompt},
        )
        if use_cache:
            hit = await cache_get(session, cache_key)
            if hit:
                run = Run(
                    id=run_id,
                    api_key_id=api_key_id,
                    route_id=route_id,
                    requested_engine=engine,
                    input_kind=doc.kind,
                    mime=doc.mime,
                    bytes=len(doc.data),
                    image_sha256=doc.sha256,
                    page_count=doc.page_count,
                    language=str(language) if language else None,
                    status="cached",
                    cache_hit=True,
                    client_ip=client_ip,
                    user_agent=user_agent,
                    idempotency_key=idempotency_key,
                    result_json=hit.get("result"),
                    routing_json=hit.get("routing"),
                    metadata_json=metadata,
                    chars=hit.get("usage", {}).get("chars", 0),
                    lines=hit.get("usage", {}).get("lines", 0),
                    words=hit.get("usage", {}).get("words", 0),
                    duration_ms=0,
                    finished_at=_utcnow(),
                )
                session.add(run)
                await session.flush()
                env = dict(hit)
                env["run_id"] = run_id
                env["cached"] = True
                env["status"] = "cached"
                return env

        # Privacy: refuse api engines
        if settings.privacy_mode:
            allow = {x.strip() for x in settings.privacy_api_allowlist.split(",") if x.strip()}
            members = [
                m
                for m in members
                if m.get("kind") == "local" or m.get("engine_id") in allow
            ]

        # Preprocess pages
        page_bytes = []
        for pb in doc.pages or [doc.data]:
            page_bytes.append(preprocess_image(pb, preprocess))

        # Multi-page: run each page and stitch
        ctx = {
            "mime": doc.mime,
            "page_count": doc.page_count,
            "languages": language if isinstance(language, list) else ([language] if language else []),
            "dimensions": (doc.width or 0, doc.height or 0),
            "handwriting": bool((options or {}).get("handwriting")),
            "tables": bool((options or {}).get("isTable") or (options or {}).get("tables")),
            "structured": bool((options or {}).get("structured")),
            "sensitive": settings.privacy_mode,
            "offline": False,
        }

        image_for_engine: Any
        if len(page_bytes) == 1:
            image_for_engine = page_bytes[0]
        else:
            image_for_engine = page_bytes  # engines that support pages list

        def execute_fn(cand: dict[str, Any], secrets: list[str], cred: dict[str, Any]) -> dict[str, Any]:
            # For multi-page, run per page and stitch if engine gets bytes
            if isinstance(image_for_engine, list) and len(image_for_engine) > 1:
                from ocrroute.engines.ocrplugin import OCRPlugin

                all_words = []
                texts = []
                y_offset = 0
                for page_idx, pb in enumerate(image_for_engine):
                    res = sync_execute_candidate(
                        cand,
                        secrets,
                        cred,
                        image=pb,
                        language=language,
                        prompt=prompt,
                        extra_options=options,
                    )
                    if res.get("FileParseExitCode", 1) == -1:
                        return res
                    for line in (res.get("TextOverlay") or {}).get("Lines") or []:
                        for w in line.get("Words") or []:
                            ww = dict(w)
                            ww["Top"] = float(ww["Top"]) + y_offset
                            ww["_page"] = page_idx + 1
                            all_words.append(ww)
                        texts.append(line.get("LineText") or "")
                    # Approximate page height offset
                    try:
                        from PIL import Image
                        from io import BytesIO

                        h = Image.open(BytesIO(pb)).size[1]
                    except Exception:
                        h = 2000
                    y_offset += h + 20
                plugin = OCRPlugin()
                stitched = plugin.buildResult(all_words)
                return stitched
            return sync_execute_candidate(
                cand,
                secrets,
                cred,
                image=image_for_engine if not isinstance(image_for_engine, list) else image_for_engine[0],
                language=language,
                prompt=prompt,
                extra_options=options,
            )

        cred_cache: dict[str, list[dict[str, Any]]] = {}

        async def credentials_for(pid: str) -> list[dict[str, Any]]:
            if pid.startswith("auto:") or pid.startswith("ad-hoc:"):
                return [{"id": None, "secret": "", "enabled": True}]
            if pid not in cred_cache:
                cred_cache[pid] = await self._credentials_for(session, pid)
            return cred_cache[pid]

        # Router is sync; credentials_for needs to be sync wrapper
        def credentials_for_sync(pid: str) -> list[dict[str, Any]]:
            if pid.startswith("auto:") or pid.startswith("ad-hoc:"):
                return [{"id": None, "secret": "", "enabled": True}]
            # Use already-loaded cache only; pre-load below
            return cred_cache.get(pid, [{"id": None, "secret": "", "enabled": True}])

        # Preload credentials
        for m in members:
            pid = m["provider_id"]
            if not (pid.startswith("auto:") or pid.startswith("ad-hoc:")):
                cred_cache[pid] = await self._credentials_for(session, pid)

        router = Router(
            execute_fn,
            breaker_threshold=settings.breaker_threshold,
            breaker_cooldown=settings.breaker_cooldown_seconds,
        )

        run = Run(
            id=run_id,
            api_key_id=api_key_id,
            route_id=route_id,
            requested_engine=engine,
            input_kind=doc.kind,
            mime=doc.mime,
            bytes=len(doc.data),
            image_sha256=doc.sha256,
            page_count=doc.page_count,
            language=str(language) if language else None,
            status="running",
            client_ip=client_ip,
            user_agent=user_agent,
            idempotency_key=idempotency_key,
            metadata_json=metadata,
        )
        session.add(run)
        await session.flush()

        try:
            outcome = router.resolve_and_run(
                members=members,
                strategy_name=strategy,
                context=ctx,
                stop_condition=stop,
                max_attempts=5,
                total_deadline_ms=120_000,
                credentials_for=credentials_for_sync,
            )
        except OcrRouteError as exc:
            run.status = "failed"
            run.error_code = exc.code.value
            run.error_message = redact_secrets(exc.message)
            run.finished_at = _utcnow()
            from ocrroute.engines.ocrplugin import OCRPlugin

            err_result = OCRPlugin.emptyResult()
            err_result["FileParseExitCode"] = -1
            err_result["ErrorMessage"] = run.error_message
            run.result_json = err_result
            await session.flush()
            return build_envelope(
                run_id=run_id,
                status="failed",
                result=err_result,
                routing={
                    "route": route or "auto",
                    "strategy": strategy,
                    "attempt_count": 1 if exc.code in (ErrorCode.BAD_INPUT, ErrorCode.UNSUPPORTED_INPUT) else 0,
                    "degraded": False,
                    "explain": (exc.details or {}).get("explain") or [],
                    "attempts": [],
                    "warnings": [],
                },
                usage={"pages": doc.page_count, "chars": 0, "lines": 0, "words": 0, "duration_ms": 0, "cost_cents": 0},
                metadata=metadata,
                error_code=exc.code.value,
                error_message=exc.message,
            )

        result = apply_postprocess(outcome["result"], options)
        result = apply_tools(result, None)

        # Persist attempts
        for a in outcome.get("attempts") or []:
            session.add(
                Attempt(
                    run_id=run_id,
                    provider_id=None if not a.get("provider") else None,
                    engine_id=a.get("engine"),
                    credential_id=a.get("credential_id"),
                    order_index=int(a.get("order") or 0),
                    status=a.get("status") or "failed",
                    duration_ms=int(a.get("duration_ms") or 0),
                    error_type=a.get("error_code"),
                    error_message=a.get("error_message"),
                    chars=int(a.get("chars") or 0),
                    cost_cents=float(a.get("cost_cents") or 0),
                    finished_at=_utcnow(),
                )
            )

        stats = outcome.get("stats") or {}
        routing = {
            "route": route or ("auto" if not engine else None) or engine,
            "strategy": strategy,
            "winning_engine": outcome.get("winning_engine"),
            "winning_provider": outcome.get("winning_provider"),
            "attempt_count": outcome.get("attempt_count", 0),
            "degraded": outcome.get("degraded", False),
            "explain": outcome.get("explain") or [],
            "attempts": outcome.get("attempts") or [],
            "options_applied": options or {},
            "warnings": [],
        }
        if outcome.get("votes"):
            routing["votes"] = outcome["votes"]

        usage = {
            "pages": doc.page_count,
            "chars": stats.get("chars", 0),
            "lines": stats.get("lines", 0),
            "words": stats.get("words", 0),
            "mean_confidence": stats.get("mean_confidence"),
            "duration_ms": outcome.get("duration_ms", 0),
            "cost_cents": outcome.get("cost_cents", 0),
        }

        run.status = outcome.get("status") or "failed"
        run.attempt_count = outcome.get("attempt_count") or 0
        run.chars = usage["chars"]
        run.lines = usage["lines"]
        run.words = usage["words"]
        run.duration_ms = usage["duration_ms"]
        run.cost_cents = float(usage["cost_cents"] or 0)
        run.result_json = result
        run.routing_json = routing
        run.finished_at = _utcnow()
        if outcome.get("error_code"):
            run.error_code = outcome["error_code"]
            run.error_message = outcome.get("error_message")

        # Artifacts
        artifact_list = []
        kinds = output or ["json", "text"]
        art_dir = settings.artifacts_dir / datetime.now(timezone.utc).strftime("%Y/%m/%d")
        art_dir.mkdir(parents=True, exist_ok=True)
        envelope_preview = build_envelope(
            run_id=run_id,
            status=run.status,
            result=result,
            routing=routing,
            usage=usage,
            metadata=metadata,
        )
        img0 = page_bytes[0] if page_bytes else doc.data
        for kind in kinds:
            try:
                data = write_artifact(
                    kind,
                    envelope_preview,
                    image_bytes=img0,
                    width=doc.width or 0,
                    height=doc.height or 0,
                )
                fname = f"{run_id}_{kind}"
                ext = {
                    "text": ".txt",
                    "json": ".json",
                    "md": ".md",
                    "csv": ".csv",
                    "xlsx": ".xlsx",
                    "hocr": ".html",
                    "alto": ".xml",
                    "docx": ".docx",
                    "pdf": ".pdf",
                    "overlay_png": ".png",
                }.get(kind, ".bin")
                fpath = art_dir / f"{fname}{ext}"
                fpath.write_bytes(data)
                art = Artifact(
                    run_id=run_id,
                    kind=kind,
                    path=str(fpath),
                    bytes=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),
                )
                session.add(art)
                artifact_list.append({"kind": kind, "url": f"/v1/runs/{run_id}/artifacts/{kind}"})
            except Exception as exc:
                log.warning("artifact_failed", kind=kind, error=str(exc))
                routing.setdefault("warnings", []).append(f"artifact {kind} failed: {exc}")

        await session.flush()

        env = build_envelope(
            run_id=run_id,
            status=run.status,
            result=result,
            routing=routing,
            usage=usage,
            artifacts=artifact_list,
            metadata=metadata,
            error_code=run.error_code,
            error_message=run.error_message,
        )

        if use_cache and run.status in ("succeeded", "cached"):
            await cache_put(
                session,
                cache_key,
                run_id=run_id,
                result=env,
                ttl_seconds=settings.cache_ttl_seconds,
            )

        return env
