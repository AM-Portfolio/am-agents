from __future__ import annotations

import base64
import json
from typing import Any

import httpx


def jwt_claims(access_token: str) -> dict[str, Any]:
    try:
        part = access_token.split(".")[1]
        padded = part + "=" * (-len(part) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def jwt_sub(access_token: str) -> str | None:
    sub = jwt_claims(access_token).get("sub")
    return str(sub) if sub else None


async def login_identity(
    identity_url: str,
    username: str,
    password: str,
    *,
    timeout: float = 30.0,
) -> dict[str, Any]:
    url = f"{identity_url.rstrip('/')}/auth/login"
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json={"username": username, "password": password})
        if response.status_code >= 400:
            detail = response.text[:500]
            raise ValueError(
                f"Identity login failed ({response.status_code}) at {url}: {detail}"
            )
        body = response.json()
        if not isinstance(body, dict) or not body.get("access_token"):
            raise ValueError("Identity login response missing access_token")
        return body
