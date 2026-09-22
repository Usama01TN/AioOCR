"""SQLAlchemy 2.0 models for OcrRoute."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ocrroute.crypto import new_ulid
from ocrroute.db.base import Base


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _id() -> str:
    return new_ulid()


class Engine(Base):
    __tablename__ = "engines"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)  # class name
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # api|local
    vendor: Mapped[str] = mapped_column(String(128), default="")
    module: Mapped[str] = mapped_column(String(256), default="")
    available: Mapped[int] = mapped_column(Integer, default=0)
    import_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    install_hint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requires_key: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_pdf: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_handwriting: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_tables: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_overlay: Mapped[bool] = mapped_column(Boolean, default=True)
    languages: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    option_schema: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    cost_model: Mapped[str] = mapped_column(String(32), default="local")
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)
    homepage: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    docs_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    quality_score: Mapped[float] = mapped_column(Float, default=0.5)
    first_seen: Mapped[str] = mapped_column(String(32), default=_utcnow)
    last_seen: Mapped[str] = mapped_column(String(32), default=_utcnow)

    providers: Mapped[list["Provider"]] = relationship(back_populates="engine")


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_id)
    engine_id: Mapped[str] = mapped_column(ForeignKey("engines.id"), nullable=False)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    weight: Mapped[int] = mapped_column(Integer, default=1)
    endpoint: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    timeout: Mapped[int] = mapped_column(Integer, default=30)
    retries: Mapped[int] = mapped_column(Integer, default=3)
    options: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    proxy: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    concurrency_limit: Mapped[int] = mapped_column(Integer, default=4)
    rpm_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rpd_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    monthly_budget_cents: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    health: Mapped[str] = mapped_column(String(32), default="unknown")
    health_checked_at: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    circuit_open_until: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    last_used_at: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), default=_utcnow)
    updated_at: Mapped[str] = mapped_column(String(32), default=_utcnow)

    engine: Mapped["Engine"] = relationship(back_populates="providers")
    credentials: Mapped[list["Credential"]] = relationship(
        back_populates="provider", cascade="all, delete-orphan"
    )


class Credential(Base):
    __tablename__ = "credentials"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_id)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), nullable=False)
    alias: Mapped[str] = mapped_column(String(128), default="")
    secret_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    exhausted_until: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), default=_utcnow)

    provider: Mapped["Provider"] = relationship(back_populates="credentials")


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    strategy: Mapped[str] = mapped_column(String(64), default="priority")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    stop_condition: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    total_deadline_ms: Mapped[int] = mapped_column(Integer, default=120_000)
    cache_ttl_seconds: Mapped[int] = mapped_column(Integer, default=86400)
    tool_chain: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), default=_utcnow)
    updated_at: Mapped[str] = mapped_column(String(32), default=_utcnow)

    members: Mapped[list["RouteMember"]] = relationship(
        back_populates="route", cascade="all, delete-orphan", order_by="RouteMember.order_index"
    )


class RouteMember(Base):
    __tablename__ = "route_members"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_id)
    route_id: Mapped[str] = mapped_column(ForeignKey("routes.id"), nullable=False)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    weight: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    condition: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    option_overrides: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    route: Mapped["Route"] = relationship(back_populates="members")
    provider: Mapped["Provider"] = relationship()


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    scopes: Mapped[Any] = mapped_column(JSON, default=list)
    route_id: Mapped[Optional[str]] = mapped_column(ForeignKey("routes.id"), nullable=True)
    rpm_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rpd_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    monthly_budget_cents: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    last_used_at: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), default=_utcnow)


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        Index("ix_runs_created_at", "created_at"),
        Index("ix_runs_status", "status"),
        Index("ix_runs_image_sha256", "image_sha256"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_id)
    api_key_id: Mapped[Optional[str]] = mapped_column(ForeignKey("api_keys.id"), nullable=True)
    route_id: Mapped[Optional[str]] = mapped_column(ForeignKey("routes.id"), nullable=True)
    requested_engine: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    input_kind: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    mime: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    image_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, default=1)
    language: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    winning_attempt_id: Mapped[Optional[str]] = mapped_column(String(26), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    chars: Mapped[int] = mapped_column(Integer, default=0)
    lines: Mapped[int] = mapped_column(Integer, default=0)
    words: Mapped[int] = mapped_column(Integer, default=0)
    mean_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    cost_cents: Mapped[float] = mapped_column(Float, default=0.0)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    client_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    routing_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), default=_utcnow)
    finished_at: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    attempts: Mapped[list["Attempt"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list["Artifact"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class Attempt(Base):
    __tablename__ = "attempts"
    __table_args__ = (
        Index("ix_attempts_run_id", "run_id"),
        Index("ix_attempts_provider_started", "provider_id", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=False)
    provider_id: Mapped[Optional[str]] = mapped_column(ForeignKey("providers.id"), nullable=True)
    engine_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    credential_id: Mapped[Optional[str]] = mapped_column(ForeignKey("credentials.id"), nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="succeeded")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retries_used: Mapped[int] = mapped_column(Integer, default=0)
    chars: Mapped[int] = mapped_column(Integer, default=0)
    cost_cents: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[str] = mapped_column(String(32), default=_utcnow)
    finished_at: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    run: Mapped["Run"] = relationship(back_populates="attempts")


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), default=_utcnow)

    run: Mapped["Run"] = relationship(back_populates="artifacts")


class CacheEntry(Base):
    __tablename__ = "cache"
    __table_args__ = (Index("ix_cache_expires_at", "expires_at"),)

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=False)
    result_json: Mapped[Any] = mapped_column(JSON, nullable=False)
    hits: Mapped[int] = mapped_column(Integer, default=0)
    bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String(32), default=_utcnow)
    expires_at: Mapped[str] = mapped_column(String(32), nullable=False)


class UsageDaily(Base):
    __tablename__ = "usage_daily"
    __table_args__ = (
        UniqueConstraint("day", "engine_id", "provider_id", "api_key_id", name="uq_usage_daily"),
        Index("ix_usage_daily_day", "day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    day: Mapped[str] = mapped_column(String(10), nullable=False)
    engine_id: Mapped[str] = mapped_column(String(128), default="")
    provider_id: Mapped[str] = mapped_column(String(26), default="")
    api_key_id: Mapped[str] = mapped_column(String(26), default="")
    runs: Mapped[int] = mapped_column(Integer, default=0)
    successes: Mapped[int] = mapped_column(Integer, default=0)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    pages: Mapped[int] = mapped_column(Integer, default=0)
    chars: Mapped[int] = mapped_column(Integer, default=0)
    cost_cents: Mapped[float] = mapped_column(Float, default=0.0)
    p50_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p95_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(256), default="")
    route_id: Mapped[Optional[str]] = mapped_column(ForeignKey("routes.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    total: Mapped[int] = mapped_column(Integer, default=0)
    done: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    options: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    webhook_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), default=_utcnow)
    finished_at: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    items: Mapped[list["JobItem"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class JobItem(Base):
    __tablename__ = "job_items"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[Optional[str]] = mapped_column(ForeignKey("runs.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    job: Mapped["Job"] = relationship(back_populates="items")


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value_json: Mapped[Any] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), default=_utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_id)
    actor: Mapped[str] = mapped_column(String(128), default="")
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    target_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    detail: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), default=_utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_id)
    username: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="admin")  # admin|operator|viewer
    totp_secret_enc: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), default=_utcnow)


class Tool(Base):
    """Reserved tools catalogue — intentionally empty in v0.1."""

    __tablename__ = "tools"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    version: Mapped[str] = mapped_column(String(32), default="0.0.0")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    options_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    installed_at: Mapped[str] = mapped_column(String(32), default=_utcnow)


class ToolRun(Base):
    """Reserved tool execution log — intentionally empty in v0.1."""

    __tablename__ = "tool_runs"
    __table_args__ = (Index("ix_tool_runs_run_id", "run_id"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=False)
    tool_id: Mapped[str] = mapped_column(ForeignKey("tools.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    output_ref: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), default=_utcnow)


class SchemaMeta(Base):
    __tablename__ = "schema_meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
