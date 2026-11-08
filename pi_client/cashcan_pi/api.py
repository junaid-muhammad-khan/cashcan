"""Thin HTTP client for the CashCan face API."""
from __future__ import annotations

import httpx


class FaceApi:
    def __init__(self, base_url: str, timeout: float = 5.0, transport: httpx.BaseTransport | None = None,
                 bin_key: str | None = None):
        headers = {"X-Bin-Key": bin_key} if bin_key else {}
        self._http = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout, transport=transport, headers=headers)

    def match(self, jpeg: bytes, session_token: str | None = None) -> dict:
        """session_token: pass the current live session so the same person can refresh without a new challenge."""
        data = {"session_token": session_token} if session_token else None
        r = self._http.post("/match", files={"frame": ("frame.jpg", jpeg, "image/jpeg")}, data=data)
        r.raise_for_status()
        return r.json()

    def liveness_frame(self, challenge_id: str, jpeg: bytes) -> dict:
        r = self._http.post(f"/liveness/{challenge_id}/frame", files={"frame": ("frame.jpg", jpeg, "image/jpeg")})
        r.raise_for_status()
        return r.json()

    def session(self, token: str) -> dict | None:
        r = self._http.get(f"/session/{token}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def interaction(self, payload: dict) -> dict:
        """Record one sorted item (needs the bin key). The same interaction_id is stored once, so retrying is safe."""
        r = self._http.post("/interactions", json=payload)
        r.raise_for_status()
        return r.json()

    def warm(self) -> bool:
        """Wake the server and load its face models (a cold start can take ~20 s). Call once at start-up, off the main thread."""
        try:
            return self._http.get("/warm", timeout=90).status_code == 200
        except httpx.HTTPError:
            return False
