"""Extract user identity from inbound Bearer JWT (no signature verify — MCP verifies)."""
from __future__ import annotations

import base64
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def bearer_token(auth_header: str) -> str:
    header = (auth_header or "").strip()
    if not header:
        return ""
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return header


def _decode_jwt_payload(token: str) -> dict[str, Any] | None:
    if not token or token.count(".") < 2:
        return None
    try:
        segment = token.split(".")[1]
        padding = "=" * (-len(segment) % 4)
        raw = base64.urlsafe_b64decode(segment + padding)
        payload = json.loads(raw.decode("utf-8"))
        return payload if isinstance(payload, dict) else None
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.debug("jwt_context: could not decode payload: %s", exc)
        return None


def jwt_subject(token: str) -> str | None:
    """Return JWT ``sub`` (or ``userId`` / ``user_id`` fallbacks)."""
    payload = _decode_jwt_payload(token)
    if not payload:
        return None
    for key in ("sub", "userId", "user_id"):
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def resolve_request_user_id(
    *,
    body_user_id: str | None,
    header_user_id: str | None,
    auth_header: str,
) -> tuple[str, str | None]:
    """
    Pick canonical user id for the request.

    Priority: JWT ``sub`` > non-empty body userId > x-user-id header > anonymous.
    Returns (canonical_user_id, jwt_sub).
    """
    token = bearer_token(auth_header)
    jwt_sub = jwt_subject(token) if token else None

    body = (body_user_id or "").strip()
    header = (header_user_id or "").strip()

    if jwt_sub:
        if body and body not in {"anonymous", "-"} and body != jwt_sub:
            logger.warning(
                "userId mismatch: body=%r jwt_sub=%r — using JWT identity",
                body,
                jwt_sub,
            )
        return jwt_sub, jwt_sub

    if body and body not in {"anonymous", "-"}:
        return body, None
    if header and header not in {"anonymous", "-"}:
        return header, None
    return "anonymous", None
