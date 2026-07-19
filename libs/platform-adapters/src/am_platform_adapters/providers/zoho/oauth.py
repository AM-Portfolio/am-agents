"""Zoho OAuth access-token resolution (refresh_token preferred)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def _accounts_base() -> str:
    return (os.environ.get("ZOHO_ACCOUNTS_BASE", "https://accounts.zoho.in")).rstrip("/")


def refresh_access_token(
    *,
    client_id: str | None = None,
    client_secret: str | None = None,
    refresh_token: str | None = None,
) -> str:
    cid = (client_id or os.environ.get("ZOHO_CLIENT_ID", "")).strip()
    secret = (client_secret or os.environ.get("ZOHO_CLIENT_SECRET", "")).strip()
    refresh = (refresh_token or os.environ.get("ZOHO_REFRESH_TOKEN", "")).strip()
    if not (cid and secret and refresh):
        raise RuntimeError(
            "ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, and ZOHO_REFRESH_TOKEN required to refresh"
        )
    body = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "client_id": cid,
            "client_secret": secret,
            "refresh_token": refresh,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{_accounts_base()}/oauth/v2/token",
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "am-platform-adapters/0.1 (ZohoOAuth)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Zoho OAuth refresh failed {exc.code}: {detail[:300]}") from exc
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise RuntimeError(f"Zoho OAuth refresh returned no access_token: {payload!r}"[:300])
    return token


def resolve_access_token(*, static_token: str = "", prefer_refresh: bool = True) -> str:
    """
    Return a usable Zoho access token.

    Prefer refresh when client credentials + refresh_token are present (tokens expire ~1h).
    Fall back to a static access token from env / caller.
    """
    has_refresh = all(
        (os.environ.get(k) or "").strip()
        for k in ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN")
    )
    if prefer_refresh and has_refresh:
        return refresh_access_token()
    token = (static_token or "").strip()
    if token:
        return token
    raise RuntimeError(
        "No Zoho access token: set ZOHO_REFRESH_TOKEN (+ client id/secret) or a static access token"
    )
