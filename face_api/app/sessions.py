"""Short-lived bin sessions. One successful face match opens a session; payouts in that
window go to the matched user, so we don't scan the face for every item."""
from __future__ import annotations

import secrets
import time

from . import config


class SessionManager:
    def __init__(self, ttl: int = config.SESSION_TTL_SECONDS, clock=time.monotonic):
        self._ttl, self._clock = ttl, clock
        self._sessions: dict[str, tuple[str, float, float]] = {}  # user, expires, live_at

    def open(self, user_id: str, live_at: float | None = None) -> tuple[str, int]:
        """live_at = when liveness was last proven (defaults to now)."""
        token, now = secrets.token_urlsafe(16), self._clock()
        self._sessions[token] = (user_id, now + self._ttl, now if live_at is None else live_at)
        return token, self._ttl

    def live_at(self, token: str) -> float | None:
        entry = self._sessions.get(token)
        return entry[2] if entry else None

    def live_age(self, token: str) -> tuple[str, float] | None:
        """(user_id, seconds since liveness was proven) for a live session, else None."""
        user = self.user_for(token)
        return (user, self._clock() - self._sessions[token][2]) if user else None

    def user_for(self, token: str) -> str | None:
        entry = self._sessions.get(token)
        if not entry:
            return None
        if self._clock() > entry[1]:
            del self._sessions[token]
            return None
        return entry[0]

    def close_user(self, user_id: str) -> None:
        for t in [t for t, (u, _, _) in self._sessions.items() if u == user_id]:
            del self._sessions[t]
