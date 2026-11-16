"""Supabase JWT verification.

Supports both Supabase token types:
- legacy HS256 tokens signed with the project JWT secret
- newer asymmetric (ES256) tokens verified via the project's JWKS endpoint

Returns an AuthContext on success; raises AuthError otherwise.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import jwt
from jwt import PyJWKClient

from app.core.config import settings


class AuthError(Exception):
    """Raised for any token validation failure. Maps to HTTP 401."""


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    email: str | None
    role: str | None
    claims: dict


_jwks_client: PyJWKClient | None = None


def _jwks() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        if not settings.supabase_url:
            raise AuthError("JWT verification not configured")
        _jwks_client = PyJWKClient(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        )
    return _jwks_client


def verify_token(token: str) -> AuthContext:
    """Validate a Supabase access token and return the caller's identity."""
    if not token:
        raise AuthError("missing token")

    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise AuthError(f"malformed token: {exc}") from exc

    alg = header.get("alg", "")
    options = {"verify_aud": True, "require": ["exp", "sub"]}

    try:
        if alg == "HS256":
            if not settings.supabase_jwt_secret:
                raise AuthError("HS256 token but no JWT secret configured")
            claims = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience=settings.jwt_audience,
                options=options,
            )
        elif alg in ("ES256", "RS256"):
            key = _jwks().get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=["ES256", "RS256"],
                audience=settings.jwt_audience,
                options=options,
            )
        else:
            raise AuthError(f"unsupported alg: {alg}")
    except AuthError:
        raise
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("token expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthError(f"invalid token: {exc}") from exc

    # Reject far-future issued-at as a cheap sanity check
    if claims.get("iat") and claims["iat"] > time.time() + 300:
        raise AuthError("token issued in the future")

    return AuthContext(
        user_id=claims["sub"],
        email=claims.get("email"),
        role=claims.get("role"),
        claims=claims,
    )
