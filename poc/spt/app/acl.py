"""PoC ACL — API keys mapped to roles (developer|agent|ci|shared)."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from fastapi import HTTPException, Request
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.config import settings
from app.db.engine import get_session, init_db, store_mode
from app.db.models import ApiKeyRow

PUBLIC_PREFIXES = (
    "/health",
    "/ready",
    "/ui",
    "/static",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/mcp",  # MCP has its own auth on mutates
)


@dataclass
class Caller:
    role: str = "developer"
    key_id: str | None = None
    key_name: str | None = None
    authenticated: bool = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def extract_raw_key(request: Request) -> str | None:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return (request.headers.get("x-spt-api-key") or "").strip() or None


def lookup_key(raw: str) -> Caller | None:
    if store_mode() == "json":
        # No DB — treat bootstrap env keys only
        for part in (settings.spt_bootstrap_keys or "").split(","):
            part = part.strip()
            if not part or ":" not in part:
                continue
            bits = part.split(":", 2)
            if len(bits) != 3:
                continue
            role, name, secret = bits
            if secrets.compare_digest(secret, raw):
                return Caller(role=role.strip().lower(), key_id="bootstrap", key_name=name, authenticated=True)
        return None
    digest = hash_key(raw)
    with get_session() as session:
        row = session.scalar(
            select(ApiKeyRow).where(ApiKeyRow.key_hash == digest, ApiKeyRow.enabled.is_(True))
        )
        if not row:
            return None
        return Caller(role=row.role, key_id=row.id, key_name=row.name, authenticated=True)


def resolve_caller(request: Request) -> Caller:
    raw = extract_raw_key(request)
    if raw:
        found = lookup_key(raw)
        if found:
            hdr_role = (request.headers.get("x-spt-role") or "").strip().lower()
            if hdr_role and hdr_role != found.role:
                # Header must match key; ignore forge attempts
                pass
            return found
        if settings.spt_acl_required:
            raise HTTPException(status_code=401, detail="Invalid SPT API key")
    # Unauthenticated: default developer for local UI when ACL not required
    hdr = (request.headers.get("x-spt-role") or "").strip().lower()
    if settings.spt_acl_required:
        raise HTTPException(status_code=401, detail="SPT API key required")
    if hdr in {"developer", "agent", "ci", "shared"}:
        return Caller(role=hdr, authenticated=False)
    return Caller(role="developer", authenticated=False)


def allows_multi_load(role: str | None, audience: str | None = None) -> bool:
    """Multi-VU only for developer role AND developer audience."""
    r = (role or "developer").lower()
    a = (audience or "developer").lower()
    return r == "developer" and a == "developer"


def enforce_execute_load(
    *,
    role: str,
    audience: str,
    vus: int | None,
    iterations: int | None,
    duration: str | None,
    preset: str | None,
) -> None:
    if allows_multi_load(role, audience):
        return
    multi = False
    if vus is not None and int(vus) > 1:
        multi = True
    if iterations is not None and int(iterations) > 1:
        multi = True
    if duration:
        multi = True
    if preset:
        multi = True
    if multi:
        raise HTTPException(
            status_code=403,
            detail="Multi-VU / duration / presets require developer role and developer audience",
        )


def seed_bootstrap_keys() -> list[dict]:
    """Create keys from SPT_BOOTSTRAP_KEYS=role:name:secret,..."""
    if store_mode() == "json":
        return []
    init_db()
    created: list[dict] = []
    raw = (settings.spt_bootstrap_keys or "").strip()
    # Always ensure a local-dev key exists when ACL off (documented default)
    defaults: list[tuple[str, str, str]] = []
    if raw:
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            bits = part.split(":", 2)
            if len(bits) != 3:
                continue
            defaults.append((bits[0].strip().lower(), bits[1].strip(), bits[2].strip()))
    else:
        defaults = [
            ("developer", "local-dev", "spt_sk_dev_localchange_me"),
            ("agent", "local-agent", "spt_sk_agent_localchange_me"),
        ]
    with get_session() as session:
        for role, name, secret in defaults:
            digest = hash_key(secret)
            existing = session.scalar(select(ApiKeyRow).where(ApiKeyRow.key_hash == digest))
            if existing:
                continue
            kid = str(uuid.uuid4())
            session.add(
                ApiKeyRow(
                    id=kid,
                    name=name,
                    key_hash=digest,
                    key_prefix=secret[:16],
                    role=role,
                    enabled=True,
                    created_at=_now(),
                )
            )
            created.append({"id": kid, "name": name, "role": role, "prefix": secret[:16]})
    return created


class AclMiddleware(BaseHTTPMiddleware):
    """Attach request.state.spt_caller; optionally require keys on mutating routes."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path or ""
        # Strip root_path if present
        root = (settings.root_path or "").rstrip("/")
        if root and path.startswith(root):
            path = path[len(root) :] or "/"
        is_public = any(path == p or path.startswith(p + "/") for p in PUBLIC_PREFIXES)
        is_mutate = request.method in {"POST", "PUT", "PATCH", "DELETE"}
        try:
            if is_public and not (is_mutate and path.startswith("/api/")):
                request.state.spt_caller = Caller(role="developer", authenticated=False)
                return await call_next(request)
            # k6 callbacks from local runner — allow without key
            if path.startswith("/api/runs/") and (
                path.endswith("/progress") or path.endswith("/sample")
            ):
                request.state.spt_caller = Caller(role="developer", authenticated=False)
                return await call_next(request)
            caller = resolve_caller(request)
            request.state.spt_caller = caller
            if settings.spt_acl_required and is_mutate and path.startswith("/api/") and not caller.authenticated:
                return JSONResponse({"detail": "SPT API key required"}, status_code=401)
            return await call_next(request)
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
