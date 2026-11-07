"""Short-lived bin sessions. One successful face match opens a session; payouts in that
window go to the matched user, so we don't scan the face for every item."""
from __future__ import annotations

import secrets
import time

from . import config


class SessionManager:
    def __init__(self, ttl: int = config.SESSION_TTL_SECONDS, clock=time.monotonic):
        self._ttl, self._clock = ttl, clock
        self._sessions: dict[str, tuple[str, float]] = {}

    def open(self, user_id: str) -> tuple[str, int]:
        token = secrets.token_urlsafe(16)
        self._sessions[token] = (user_id, self._clock() + self._ttl)
        return token, self._ttl

    def user_for(self, token: str) -> str | None:
        entry = self._sessions.get(token)
        if not entry:
            return None
        if self._clock() > entry[1]:
            del self._sessions[token]
            return None
        return entry[0]

    def close_user(self, user_id: str) -> None:
        for t in [t for t, (u, _) in self._sessions.items() if u == user_id]:
            del self._sessions[t]
