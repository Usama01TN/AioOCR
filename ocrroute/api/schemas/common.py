"""Shared Pydantic schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PreprocessOptions(BaseModel):
    auto_rotate: bool = False
    grayscale: bool = False
    denoise: bool = False
    contrast: bool = False
    upscale: bool = False
    region: list[int] | None = None


class StopCondition(BaseModel):
    min_chars: int | None = None
    min_mean_confidence: float | None = None
    require_overlay: bool | None = None


class OcrRequest(BaseModel):
    url: str | None = None
    base64: str | None = None
    route: str | None = None
    engine: str | None = None
    provider_id: str | None = None
    language: Any | None = None
    pages: str | None = None
    prompt: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    preprocess: PreprocessOptions | None = None
    output: list[str] = Field(default_factory=lambda: ["json", "text"])
    stop_condition: StopCondition | None = None
    cache: bool = True
    async_mode: bool = Field(default=False, alias="async")
    webhook_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class BatchRequest(BaseModel):
    items: list[dict[str, Any]]
    route: str | None = None
    engine: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    output: list[str] = Field(default_factory=lambda: ["json", "text"])
    webhook_url: str | None = None
    name: str = "batch"


class ProviderCreate(BaseModel):
    engine_id: str
    label: str
    enabled: bool = True
    priority: int = 100
    weight: int = 1
    endpoint: str | None = None
    model: str | None = None
    language: str | None = None
    timeout: int = 30
    retries: int = 3
    options: dict[str, Any] = Field(default_factory=dict)
    proxy: dict[str, Any] | None = None
    concurrency_limit: int = 4
    rpm_limit: int | None = None
    rpd_limit: int | None = None
    monthly_budget_cents: float | None = None
    notes: str | None = None


class ProviderUpdate(BaseModel):
    label: str | None = None
    enabled: bool | None = None
    priority: int | None = None
    weight: int | None = None
    endpoint: str | None = None
    model: str | None = None
    language: str | None = None
    timeout: int | None = None
    retries: int | None = None
    options: dict[str, Any] | None = None
    proxy: dict[str, Any] | None = None
    concurrency_limit: int | None = None
    rpm_limit: int | None = None
    rpd_limit: int | None = None
    monthly_budget_cents: float | None = None
    notes: str | None = None


class CredentialCreate(BaseModel):
    provider_id: str
    alias: str = ""
    secret: str
    order_index: int = 0
    enabled: bool = True


class RouteCreate(BaseModel):
    name: str
    description: str = ""
    strategy: str = "priority"
    enabled: bool = True
    is_default: bool = False
    stop_condition: dict[str, Any] | None = None
    max_attempts: int = 5
    total_deadline_ms: int = 120_000
    cache_ttl_seconds: int = 86400
    members: list[dict[str, Any]] = Field(default_factory=list)


class RouteUpdate(BaseModel):
    description: str | None = None
    strategy: str | None = None
    enabled: bool | None = None
    is_default: bool | None = None
    stop_condition: dict[str, Any] | None = None
    max_attempts: int | None = None
    total_deadline_ms: int | None = None
    cache_ttl_seconds: int | None = None


class RouteMemberCreate(BaseModel):
    provider_id: str
    order_index: int = 0
    weight: int = 1
    enabled: bool = True
    condition: dict[str, Any] | None = None
    option_overrides: dict[str, Any] | None = None


class SimulateRequest(BaseModel):
    mime: str | None = "image/png"
    language: Any | None = None
    pages: int = 1
    width: int = 800
    height: int = 600
    handwriting: bool = False
    tables: bool = False
    sensitive: bool = False
    offline: bool = False


class ApiKeyCreate(BaseModel):
    name: str
    scopes: list[str] = Field(default_factory=lambda: ["ocr:write", "ocr:read"])
    route_id: str | None = None
    rpm_limit: int | None = None
    rpd_limit: int | None = None
    monthly_budget_cents: float | None = None
    expires_at: str | None = None


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "admin"
