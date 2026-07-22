from __future__ import annotations

import os
from typing import Any

from app.config import settings
from app.identity_client import jwt_sub, login_identity


def sanitize_auth_env(auth: dict[str, Any] | None) -> dict[str, Any]:
    """Safe auth metadata for UI / run storage (no token or password)."""
    src = dict(auth or {})
    out: dict[str, Any] = {}
    for key in ("username", "user_id", "identity_url"):
        val = src.get(key)
        if val:
            out[key] = val
    if src.get("token") or src.get("password"):
        out["authenticated"] = True
    elif out.get("username"):
        out["authenticated"] = False
    return out


async def ensure_auth_env(config: dict[str, Any]) -> dict[str, Any]:
    """Fetch JWT from am-identity when username/password are configured."""
    payloads = dict(config.get("payloads") or {})
    auth = dict(payloads.get("auth_env") or {})

    if auth.get("token") or os.environ.get("SPT_AUTH_TOKEN"):
        if not auth.get("username"):
            auth["username"] = (
                os.environ.get("SPT_AUTH_USERNAME") or settings.spt_auth_username or ""
            )
        token = str(auth.get("token") or os.environ.get("SPT_AUTH_TOKEN") or "")
        if token and not auth.get("user_id"):
            sub = jwt_sub(token)
            if sub:
                auth["user_id"] = sub
        payloads["auth_env"] = auth
        config["payloads"] = payloads
        return config

    username = str(
        auth.get("username")
        or os.environ.get("SPT_AUTH_USERNAME")
        or settings.spt_auth_username
        or ""
    ).strip()
    password = str(
        auth.get("password")
        or os.environ.get("SPT_AUTH_PASSWORD")
        or settings.spt_auth_password
        or ""
    )
    identity_url = str(
        auth.get("identity_url")
        or os.environ.get("SPT_IDENTITY_URL")
        or settings.spt_identity_url
        or ""
    ).strip()

    if not username or not password or not identity_url:
        payloads["auth_env"] = auth
        config["payloads"] = payloads
        return config

    token_body = await login_identity(identity_url, username, password)
    token = str(token_body["access_token"])
    auth["token"] = token
    auth["username"] = username
    auth["identity_url"] = identity_url
    sub = jwt_sub(token)
    if sub:
        auth["user_id"] = sub
    payloads["auth_env"] = auth
    config["payloads"] = payloads
    return config
