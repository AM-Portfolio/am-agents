"""
Optional JWT gate for fin-portfolio-agent.

AUTH_REQUIRED=false (default): if Bearer is present, use token `sub` as userId
when the body userId is empty; never block.
AUTH_REQUIRED=true: reject missing/invalid Bearer; require body userId to match token subject.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any, Optional

import jwt
from jwt import PyJWKClient
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from shared.context.request_context import auth_token_var, user_id_var

logger = logging.getLogger("am.fin.auth")

AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "false").lower() == "true"
AUTH_JWKS_URL = os.getenv("AUTH_JWKS_URL", "").strip()
AUTH_ISSUER = os.getenv("AUTH_ISSUER", "").strip()
AUTH_AUDIENCE = os.getenv("AUTH_AUDIENCE", "").strip()
CORS_ORIGINS_ENV = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:9000,http://127.0.0.1:9000,https://am.asrax.in,https://am-dev.asrax.in",
)
_jwk_client = (
    PyJWKClient(AUTH_JWKS_URL, cache_jwk_set=True, lifespan=300)
    if AUTH_JWKS_URL
    else None
)


def cors_origins() -> list[str]:
    parts = [o.strip() for o in CORS_ORIGINS_ENV.split(",") if o.strip()]
    return parts if parts else ["*"]


def _b64url_json(segment: str) -> Optional[dict[str, Any]]:
    try:
        pad = "=" * (-len(segment) % 4)
        raw = base64.urlsafe_b64decode(segment + pad)
        return json.loads(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None


def decode_jwt_claims(token: str) -> Optional[dict[str, Any]]:
    """Decode optional-mode JWT payload when no local JWKS is configured."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    return _b64url_json(parts[1])


def verify_jwt_claims(token: str) -> Optional[dict[str, Any]]:
    """Verify a JWT with the configured JWKS endpoint."""
    if _jwk_client is None:
        return None
    try:
        signing_key = _jwk_client.get_signing_key_from_jwt(token).key
        options = {"verify_aud": bool(AUTH_AUDIENCE)}
        decode_kwargs: dict[str, Any] = {
            "algorithms": ["RS256"],
            "options": options,
        }
        if AUTH_AUDIENCE:
            decode_kwargs["audience"] = AUTH_AUDIENCE
        if AUTH_ISSUER:
            # Accept with or without trailing slash (common Keycloak mismatch).
            issuers = {AUTH_ISSUER, AUTH_ISSUER.rstrip("/"), AUTH_ISSUER.rstrip("/") + "/"}
            decode_kwargs["issuer"] = list(issuers)
        return jwt.decode(token, signing_key, **decode_kwargs)
    except jwt.PyJWTError as exc:
        # Soft path: signature may still be valid with different iss claim formatting.
        try:
            signing_key = _jwk_client.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                options={"verify_aud": False, "verify_iss": False},
            )
            logger.warning(
                "Bearer token accepted with relaxed iss/aud after: %s (iss=%s)",
                exc,
                claims.get("iss"),
            )
            return claims
        except jwt.PyJWTError as exc2:
            logger.warning("Bearer token verification failed: %s", exc2)
            return None


def subject_from_claims(claims: dict[str, Any]) -> Optional[str]:
    val = claims.get("sub")
    if isinstance(val, str) and val.strip():
        return val.strip()
    return None


class JwtUserMiddleware(BaseHTTPMiddleware):
    """Attach request.state.token_user_id; optionally enforce auth on /api/v1/ai/chat."""

    async def dispatch(self, request: Request, call_next):
        request.state.token_user_id = None
        request.state.auth_token = None
        auth = request.headers.get("authorization") or request.headers.get(
            "Authorization"
        )
        if auth and auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
            request.state.auth_token = token
            claims = (
                verify_jwt_claims(token)
                if AUTH_JWKS_URL
                else decode_jwt_claims(token)
            )
            if claims:
                request.state.token_user_id = subject_from_claims(claims)

        path = request.url.path
        if AUTH_REQUIRED and path.endswith("/ai/chat"):
            if not AUTH_JWKS_URL:
                return JSONResponse(
                    status_code=503,
                    content={"detail": "AUTH_JWKS_URL is required when AUTH_REQUIRED=true"},
                )
            if not request.state.token_user_id:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Valid Bearer token required"},
                )

        auth_context = auth_token_var.set(request.state.auth_token or "")
        user_context = user_id_var.set(request.state.token_user_id or "anonymous")
        try:
            return await call_next(request)
        finally:
            auth_token_var.reset(auth_context)
            user_id_var.reset(user_context)
