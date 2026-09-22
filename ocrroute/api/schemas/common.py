"""Shared Pydantic schemas."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class PreprocessOptions(BaseModel):
    auto_rotate: bool = False
    grayscale: bool = False
    denoise: bool = False
    contrast: bool = False
    upscale: bool = False
    region: Optional[list[int]] = None


class StopCondition(BaseModel):
    min_chars: Optional[int] = None
    min_mean_confidence: Optional[float] = None
    require_overlay: Optional[bool] = None


class OcrRequest(BaseModel):
    url: Optional[str] = None
    base64: Optional[str] = None
    route: Optional[str] = None
    engine: Optional[str] = None
    provider_id: Optional[str] = None
    language: Optional[Any] = None
    pages: Optional[str] = None
    prompt: Optional[str] = None
    options: dict[str, Any] = Field(default_factory=dict)
    preprocess: Optional[PreprocessOptions] = None
    output: list[str] = Field(default_factory=lambda: ["json", "text"])
    stop_condition: Optional[StopCondition] = None
    cache: bool = True
    async_mode: bool = Field(default=False, alias="async")
    webhook_url: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class BatchRequest(BaseModel):
    items: list[dict[str, Any]]
    route: Optional[str] = None
    engine: Optional[str] = None
    options: dict[str, Any] = Field(default_factory=dict)
    output: list[str] = Field(default_factory=lambda: ["json", "text"])
    webhook_url: Optional[str] = None
    name: str = "batch"


class ProviderCreate(BaseModel):
    engine_id: str
    label: str
    enabled: bool = True
    priority: int = 100
    weight: int = 1
    endpoint: Optional[str] = None
    model: Optional[str] = None
    language: Optional[str] = None
    timeout: int = 30
    retries: int = 3
    options: dict[str, Any] = Field(default_factory=dict)
    proxy: Optional[dict[str, Any]] = None
    concurrency_limit: int = 4
    rpm_limit: Optional[int] = None
    rpd_limit: Optional[int] = None
    monthly_budget_cents: Optional[float] = None
    notes: Optional[str] = None


class ProviderUpdate(BaseModel):
    label: Optional[str] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    weight: Optional[int] = None
    endpoint: Optional[str] = None
    model: Optional[str] = None
    language: Optional[str] = None
    timeout: Optional[int] = None
    retries: Optional[int] = None
    options: Optional[dict[str, Any]] = None
    proxy: Optional[dict[str, Any]] = None
    concurrency_limit: Optional[int] = None
    rpm_limit: Optional[int] = None
    rpd_limit: Optional[int] = None
    monthly_budget_cents: Optional[float] = None
    notes: Optional[str] = None


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
    stop_condition: Optional[dict[str, Any]] = None
    max_attempts: int = 5
    total_deadline_ms: int = 120_000
    cache_ttl_seconds: int = 86400
    members: list[dict[str, Any]] = Field(default_factory=list)


class RouteUpdate(BaseModel):
    description: Optional[str] = None
    strategy: Optional[str] = None
    enabled: Optional[bool] = None
    is_default: Optional[bool] = None
    stop_condition: Optional[dict[str, Any]] = None
    max_attempts: Optional[int] = None
    total_deadline_ms: Optional[int] = None
    cache_ttl_seconds: Optional[int] = None


class RouteMemberCreate(BaseModel):
    provider_id: str
    order_index: int = 0
    weight: int = 1
    enabled: bool = True
    condition: Optional[dict[str, Any]] = None
    option_overrides: Optional[dict[str, Any]] = None


class SimulateRequest(BaseModel):
    mime: Optional[str] = "image/png"
    language: Optional[Any] = None
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
    route_id: Optional[str] = None
    rpm_limit: Optional[int] = None
    rpd_limit: Optional[int] = None
    monthly_budget_cents: Optional[float] = None
    expires_at: Optional[str] = None


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "admin"
