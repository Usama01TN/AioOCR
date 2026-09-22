"""Fernet secret encryption for credentials at rest."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets

from cryptography.fernet import Fernet, InvalidToken

from ocrroute.config import Settings, get_settings


def _derive_fernet_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def ensure_secret_key(settings: Settings | None = None) -> str:
    """Return the master secret, generating ``~/.ocrroute/secret.key`` if needed."""
    settings = settings or get_settings()
    if settings.secret_key:
        return settings.secret_key
    path = settings.secret_key_path
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    settings.ensure_dirs()
    key = secrets.token_urlsafe(48)
    path.write_text(key, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


class SecretBox:
    """Encrypt / decrypt credential blobs."""

    def __init__(self, secret: str | None = None, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        material = secret or ensure_secret_key(settings)
        self._fernet = Fernet(_derive_fernet_key(material))

    def encrypt(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, blob: bytes) -> str:
        try:
            return self._fernet.decrypt(blob).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Unable to decrypt secret (wrong OCRROUTE_SECRET_KEY?)") from exc

    @staticmethod
    def mask(secret: str, visible: int = 4) -> str:
        if not secret:
            return ""
        if len(secret) <= visible:
            return "…" + secret
        return "…" + secret[-visible:]


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Return (raw_key, key_hash, key_prefix). Prefix is ocrr_ + first 8 of random."""
    random_part = secrets.token_urlsafe(24).replace("-", "").replace("_", "")[:32]
    raw = f"ocrr_{random_part}"
    return raw, hash_api_key(raw), raw[:12]


def new_ulid() -> str:
    """Generate a new ULID string."""
    try:
        from ulid import ULID

        return str(ULID())
    except Exception:
        # Fallback: time-sortable-ish random id
        import time

        ts = int(time.time() * 1000)
        return f"{ts:011x}{secrets.token_hex(10)}"
