from __future__ import annotations

from ocrroute.crypto import SecretBox, generate_api_key, hash_api_key


def test_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("OCRROUTE_HOME", str(tmp_path))
    monkeypatch.setenv("OCRROUTE_SECRET_KEY", "unit-test-secret-key-32bytes-long!!")
    from ocrroute.config import reset_settings_cache

    reset_settings_cache()
    box = SecretBox(secret="unit-test-secret-key-32bytes-long!!")
    blob = box.encrypt("super-secret")
    assert box.decrypt(blob) == "super-secret"
    assert "secret" not in box.mask("super-secret")
    assert box.mask("super-secret").startswith("…")


def test_api_key():
    raw, h, prefix = generate_api_key()
    assert raw.startswith("ocrr_")
    assert hash_api_key(raw) == h
    assert prefix.startswith("ocrr_")
