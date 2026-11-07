"""Thin HTTP client for the CashCan face API."""
from __future__ import annotations

import httpx


class FaceApi:
    def __init__(self, base_url: str, timeout: float = 5.0, transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout, transport=transport)

    def match(self, jpeg: bytes) -> dict:
        r = self._http.post("/match", files={"frame": ("frame.jpg", jpeg, "image/jpeg")})
        r.raise_for_status()
        return r.json()

    def session(self, token: str) -> dict | None:
        r = self._http.get(f"/session/{token}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
