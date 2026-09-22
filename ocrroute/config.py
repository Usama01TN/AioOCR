"""OcrRoute settings via pydantic-settings (OCRROUTE_* env vars)."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_home() -> Path:
    override = os.environ.get("OCRROUTE_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".ocrroute"


class Settings(BaseSettings):
    """Runtime configuration. All fields map to OCRROUTE_* environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="OCRROUTE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    home: Path = Field(default_factory=default_home)
    host: str = "0.0.0.0"
    port: int = 20256
    panel_port: int = 20257
    split_panel: bool = False
    base_path: str = ""
    secret_key: str = ""
    database_url: str = ""
    log_level: str = "INFO"
    log_json: bool = True
    workers: int = 1
    reload: bool = False

    # Concurrency / limits
    global_concurrency: int = 32
    queue_size: int = 256
    max_upload_bytes: int = 50 * 1024 * 1024
    max_pixels: int = 100_000_000
    max_pages: int = 200
    download_timeout: int = 30
    download_max_bytes: int = 50 * 1024 * 1024

    # Circuit breaker
    breaker_threshold: int = 5
    breaker_cooldown_seconds: int = 120

    # Cache / retention
    cache_ttl_seconds: int = 86400
    cache_enabled: bool = True
    log_retention_days: int = 30
    store_inputs: bool = False
    privacy_mode: bool = False

    # SSRF
    ssrf_allowlist: str = ""
    ssrf_denylist: str = ""
    allow_private_urls: bool = False

    # Panel auth
    panel_session_ttl_hours: int = 24
    panel_login_max_attempts: int = 10
    panel_login_lockout_seconds: int = 300
    trusted_header_auth: bool = False
    trusted_header_name: str = "X-Forwarded-User"

    # CORS
    cors_origins: str = ""

    # Privacy allow-list for API engines when privacy_mode is on
    privacy_api_allowlist: str = ""

    @property
    def data_dir(self) -> Path:
        return self.home

    @property
    def db_path(self) -> Path:
        if self.database_url and self.database_url.startswith("sqlite"):
            # sqlite+aiosqlite:////abs/path
            raw = self.database_url.split(":///", 1)[-1]
            return Path(raw)
        return self.home / "ocrroute.db"

    @property
    def async_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        path = self.db_path
        return f"sqlite+aiosqlite:///{path}"

    @property
    def artifacts_dir(self) -> Path:
        return self.home / "artifacts"

    @property
    def secret_key_path(self) -> Path:
        return self.home / "secret.key"

    @property
    def cors_origin_list(self) -> list[str]:
        if not self.cors_origins.strip():
            return []
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def ensure_dirs(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.home, 0o700)
        except OSError:
            pass

    def resolved_secret_key(self) -> str:
        if self.secret_key:
            return self.secret_key
        path = self.secret_key_path
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        # Generated on first use by crypto module.
        return ""

    def model_dump_public(self) -> dict[str, Any]:
        data = self.model_dump()
        data.pop("secret_key", None)
        return data


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings


def reset_settings_cache() -> None:
    get_settings.cache_clear()
