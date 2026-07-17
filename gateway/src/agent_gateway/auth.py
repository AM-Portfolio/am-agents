"""Bearer token auth for gateway."""

from __future__ import annotations

import os

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_scheme = HTTPBearer(auto_error=False)


def require_token(
    creds: HTTPAuthorizationCredentials | None = Security(_scheme),
) -> str:
    expected = os.getenv("GATEWAY_API_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="GATEWAY_API_TOKEN not configured")
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Bearer token required")
    if creds.credentials != expected:
        raise HTTPException(status_code=403, detail="invalid token")
    return creds.credentials
