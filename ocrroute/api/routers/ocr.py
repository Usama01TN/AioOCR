"""OCR endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from ocrroute.api.deps import db_session, ocr_service
from ocrroute.api.schemas.common import BatchRequest, OcrRequest
from ocrroute.api.security import AuthContext, require_scope
from ocrroute.crypto import new_ulid
from ocrroute.db.models import Job, JobItem
from ocrroute.errors import ErrorCode, OcrRouteError, http_status_for
from ocrroute.runtime.service import OcrService

router = APIRouter(tags=["ocr"])


def _raise_from_envelope(env: dict[str, Any]) -> None:
    if env.get("status") == "failed" and env.get("error_code"):
        code = env["error_code"]
        # Still return body; caller uses JSONResponse with status
        pass


@router.post("/ocr")
async def ocr_sync(
    request: Request,
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("ocr:write")),
    service: OcrService = Depends(ocr_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    no_cache: str | None = Header(default=None, alias="X-OcrRoute-No-Cache"),
    file: UploadFile | None = File(default=None),
    # JSON body fields also accepted via form for multipart
) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    body: dict[str, Any] = {}
    raw_bytes = None
    filename = None

    if "multipart/form-data" in content_type:
        form = await request.form()
        body = {k: form.get(k) for k in form.keys() if k != "file"}
        # coerce
        for k in list(body.keys()):
            if body[k] == "":
                body[k] = None
        if "options" in body and isinstance(body["options"], str):
            import json

            try:
                body["options"] = json.loads(body["options"])
            except Exception:
                body["options"] = {}
        up = form.get("file")
        if up is not None and hasattr(up, "read"):
            raw_bytes = await up.read()  # type: ignore[misc]
            filename = getattr(up, "filename", None)
    else:
        try:
            body = await request.json()
        except Exception:
            body = {}

    try:
        req = OcrRequest.model_validate(body)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail={"error_code": ErrorCode.VALIDATION.value, "error_message": str(exc)},
        ) from exc

    try:
        env = await service.run_ocr(
            session,
            raw=raw_bytes,
            url=req.url,
            base64_data=req.base64,
            route=req.route,
            engine=req.engine,
            provider_id=req.provider_id,
            language=req.language,
            pages=req.pages,
            prompt=req.prompt,
            options=req.options,
            preprocess=req.preprocess.model_dump() if req.preprocess else None,
            output=req.output,
            stop_condition=req.stop_condition.model_dump(exclude_none=True) if req.stop_condition else None,
            cache=req.cache,
            metadata=req.metadata,
            api_key_id=auth.key_id,
            api_key_route_id=auth.route_id,
            client_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            idempotency_key=idempotency_key,
            no_cache_header=no_cache == "1",
        )
    except OcrRouteError as exc:
        raise HTTPException(
            status_code=exc.http_status,
            detail=exc.to_dict(),
        ) from exc

    return env


@router.post("/ocr/async")
async def ocr_async(
    request: Request,
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("ocr:write")),
) -> dict[str, Any]:
    # Enqueue as a single-item job for simplicity
    try:
        body = await request.json()
    except Exception:
        body = {}
    run_id = new_ulid()
    job = Job(
        id=new_ulid(),
        name="async-ocr",
        status="queued",
        total=1,
        options=body,
    )
    session.add(job)
    item = JobItem(job_id=job.id, source=body.get("url") or body.get("path") or "inline", status="queued", order_index=0)
    session.add(item)
    await session.flush()

    # Fire and forget processing
    from ocrroute.runtime.jobs import get_job_runner
    from ocrroute.runtime.service import OcrService
    from ocrroute.db.session import get_session_factory

    async def _run() -> None:
        factory = get_session_factory()
        async with factory() as s:
            svc = OcrService()
            try:
                env = await svc.run_ocr(
                    s,
                    url=body.get("url"),
                    base64_data=body.get("base64"),
                    route=body.get("route"),
                    engine=body.get("engine"),
                    language=body.get("language"),
                    options=body.get("options") or {},
                    api_key_id=auth.key_id,
                    metadata={"async": True, "job_id": job.id},
                )
                item_row = await s.get(JobItem, item.id)
                if item_row:
                    item_row.status = env.get("status") or "succeeded"
                    item_row.run_id = env.get("run_id")
                j = await s.get(Job, job.id)
                if j:
                    j.done = 1
                    j.status = "succeeded"
                    j.finished_at = env.get("run_id") and __import__("datetime").datetime.now(
                        __import__("datetime").timezone.utc
                    ).replace(microsecond=0).isoformat()
                await s.commit()
            except Exception as exc:
                item_row = await s.get(JobItem, item.id)
                if item_row:
                    item_row.status = "failed"
                    item_row.error_message = str(exc)
                j = await s.get(Job, job.id)
                if j:
                    j.failed = 1
                    j.status = "failed"
                await s.commit()

    get_job_runner().start(job.id, _run())
    return {"job_id": job.id, "status": "queued", "run_id": None}


@router.post("/batch")
async def batch_create(
    body: BatchRequest,
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("ocr:write")),
) -> dict[str, Any]:
    job = Job(
        id=new_ulid(),
        name=body.name,
        status="queued",
        total=len(body.items),
        options={"route": body.route, "engine": body.engine, "options": body.options, "output": body.output},
        webhook_url=body.webhook_url,
    )
    session.add(job)
    for i, it in enumerate(body.items):
        src = it.get("url") or it.get("path") or it.get("source") or f"item-{i}"
        session.add(JobItem(job_id=job.id, source=str(src), status="queued", order_index=i))
    await session.flush()

    from ocrroute.runtime.jobs import get_job_runner
    from ocrroute.runtime.service import OcrService
    from ocrroute.runtime.webhooks import deliver_webhook
    from ocrroute.db.session import get_session_factory
    from datetime import datetime, timezone

    async def _run_batch() -> None:
        factory = get_session_factory()
        async with factory() as s:
            j = await s.get(Job, job.id)
            if not j:
                return
            j.status = "running"
            await s.commit()
            items = (
                await s.execute(
                    __import__("sqlalchemy", fromlist=["select"]).select(JobItem).where(JobItem.job_id == job.id).order_by(JobItem.order_index)
                )
            ).scalars().all()
            svc = OcrService()
            done = failed = 0
            for it in items:
                try:
                    env = await svc.run_ocr(
                        s,
                        url=it.source if it.source.startswith("http") else None,
                        path=it.source if not it.source.startswith("http") else None,
                        route=body.route,
                        engine=body.engine,
                        options=body.options,
                        output=body.output,
                        api_key_id=auth.key_id,
                        metadata={"job_id": job.id},
                    )
                    it.status = env.get("status") or "succeeded"
                    it.run_id = env.get("run_id")
                    if env.get("status") == "failed":
                        failed += 1
                        it.error_message = env.get("error_message")
                    else:
                        done += 1
                except Exception as exc:
                    it.status = "failed"
                    it.error_message = str(exc)
                    failed += 1
                j.done = done
                j.failed = failed
                await s.commit()
            j.status = "succeeded" if failed == 0 else ("failed" if done == 0 else "succeeded")
            j.finished_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            await s.commit()
            if body.webhook_url:
                await deliver_webhook(
                    body.webhook_url,
                    {"job_id": job.id, "status": j.status, "done": done, "failed": failed},
                )

    get_job_runner().start(job.id, _run_batch())
    return {"job_id": job.id, "status": "queued", "total": job.total}
