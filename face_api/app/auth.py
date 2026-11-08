"""Auth0 access-token check and per-bin API keys."""
from __future__ import annotations

import secrets

from fastapi import Header, HTTPException

from . import config


class TokenVerifier:
    """Verifies an Auth0 RS256 access token (signature via the tenant's JWKS, issuer, audience, expiry) and returns its `sub`."""

    def __init__(self, domain: str, audience: str, key_resolver=None):
        import jwt

        self.domain, self.audience = domain, audience
        self._jwt = jwt
        self._keys = key_resolver or jwt.PyJWKClient(f"https://{domain}/.well-known/jwks.json", cache_keys=True)

    def sub(self, token: str) -> str:
        try:
            key = self._keys.get_signing_key_from_jwt(token).key
            claims = self._jwt.decode(token, key, algorithms=["RS256"], audience=self.audience,
                                      issuer=f"https://{self.domain}/", options={"require": ["exp", "sub", "iss", "aud"]})
        except Exception as e:  # any failure (bad signature, expired, wrong audience, JWKS unreachable) is a 401
            raise HTTPException(401, f"Invalid token: {type(e).__name__}") from e
        return claims["sub"]


def bearer(authorization: str | None = Header(None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer token.")
    return authorization[7:].strip()


def bin_for_key(key: str | None, configured: str | None = None) -> str | None:
    """bin_id for a valid X-Bin-Key, else None. Constant-time comparison."""
    found = None
    for pair in (config.BIN_API_KEYS if configured is None else configured).split(","):
        bin_id, _, k = pair.strip().partition(":")
        if bin_id and k and key and secrets.compare_digest(k, key):
            found = bin_id
    return found
