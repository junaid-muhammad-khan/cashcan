"""Short-lived bin sessions. One successful face match (+ liveness) opens a session; items dropped in that window are credited
to the matched user, so we don't scan the face for every item.

A session token is SIGNED, not stored: "s1.<payload>.<signature>", where the payload holds the user, the expiry, when liveness was
proven, when it was issued and a random id, and the signature is HMAC-SHA256 with SESSION_SECRET. Any server instance holding the
same secret can check it, so on Vercel `/match`, `/liveness/.../frame` and `/interactions` may each land on a different instance.
(The old tokens lived in one instance's memory, so a drop that reached another instance was recorded as "not recognised".)

Times are wall-clock (time.time) because they must mean the same thing on every instance.

Revocation (close_user, after a face is deleted or replaced) is only local to the instance that handled the delete: another
instance would still accept that user's token until it expires (SESSION_TTL_SECONDS, 60 s by default). The user's face data is
gone at that point, so no new session can be opened for them.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time

from . import config

log = logging.getLogger("cashcan.sessions")
PREFIX = "s1"


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class SessionManager:
    def __init__(self, ttl: int = config.SESSION_TTL_SECONDS, clock=time.time, secret: str | None = None):
        self._ttl, self._clock = ttl, clock
        key = config.SESSION_SECRET if secret is None else secret
        if not key:  # still works on one instance (like before); tokens from other instances are refused
            log.warning("SESSION_SECRET is not set: bin sessions are only valid on the server instance that issued them.")
            key = secrets.token_urlsafe(32)
        self._key = key.encode()
        self._revoked: dict[str, float] = {}   # user_id -> revoked at (this instance only)

    # ---- tokens
    def _sign(self, payload: str) -> str:
        return _b64(hmac.new(self._key, f"{PREFIX}.{payload}".encode(), hashlib.sha256).digest())

    def _claims(self, token: str | None) -> dict | None:
        """The verified, unexpired, unrevoked claims of a token, else None. Never raises on bad input."""
        if not token or not isinstance(token, str) or len(token) > 1024:
            return None
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != PREFIX:
            return None
        if not hmac.compare_digest(self._sign(parts[1]), parts[2]):
            return None
        try:
            c = json.loads(_unb64(parts[1]))
            user, exp, live, issued, sid = str(c["u"]), float(c["e"]), float(c["l"]), float(c["i"]), str(c["n"])
        except (ValueError, KeyError, TypeError):
            return None
        if self._clock() > exp:
            return None
        if user in self._revoked and issued <= self._revoked[user]:
            return None
        return {"user_id": user, "expires": exp, "live_at": live, "issued": issued, "session_id": sid}

    # ---- interface used by the API (unchanged from the in-memory version)
    def open(self, user_id: str, live_at: float | None = None) -> tuple[str, int]:
        """A new token for user_id, valid for the TTL. live_at = when liveness was last proven (defaults to now)."""
        now = self._clock()
        payload = _b64(json.dumps({"u": user_id, "e": round(now + self._ttl, 3), "l": round(now if live_at is None else live_at, 3),
                                   "i": round(now, 3), "n": secrets.token_hex(4)}, separators=(",", ":")).encode())
        return f"{PREFIX}.{payload}.{self._sign(payload)}", self._ttl

    def live_at(self, token: str) -> float | None:
        c = self._claims(token)
        return c["live_at"] if c else None

    def live_age(self, token: str) -> tuple[str, float] | None:
        """(user_id, seconds since liveness was proven) for a live session, else None."""
        c = self._claims(token)
        return (c["user_id"], self._clock() - c["live_at"]) if c else None

    def user_for(self, token: str) -> str | None:
        c = self._claims(token)
        return c["user_id"] if c else None

    def session_id(self, token: str) -> str | None:
        """A short random id for the session (stored with each interaction instead of the token)."""
        c = self._claims(token)
        return c["session_id"] if c else None

    def close_user(self, user_id: str) -> None:
        """Refuse this user's existing tokens on this instance (see the module note on other instances)."""
        self._revoked[user_id] = self._clock()
