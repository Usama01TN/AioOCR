"""HTTP client used by desktop workers (requests in QThread)."""
from __future__ import annotations

from typing import Any

import requests


class ApiClient:
    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = requests.Session()

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def get(self, path: str, **kwargs: Any) -> Any:
        r = self.session.get(self.base_url + path, headers=self._headers(), timeout=60, **kwargs)
        r.raise_for_status()
        return r.json()

    def post(self, path: str, **kwargs: Any) -> Any:
        r = self.session.post(self.base_url + path, headers=self._headers(), timeout=300, **kwargs)
        r.raise_for_status()
        return r.json()

    def ocr_file(self, path: str, engine: str | None = None, route: str | None = None) -> dict[str, Any]:
        data = {}
        if engine:
            data["engine"] = engine
        if route:
            data["route"] = route
        with open(path, "rb") as fh:
            r = self.session.post(
                self.base_url + "/v1/ocr",
                headers=self._headers(),
                files={"file": fh},
                data=data,
                timeout=300,
            )
        r.raise_for_status()
        return r.json()
