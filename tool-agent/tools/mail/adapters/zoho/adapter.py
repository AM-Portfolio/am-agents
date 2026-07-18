from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def _refresh_access_token() -> str:
    cid = os.environ.get("ZOHO_CLIENT_ID", "").strip()
    secret = os.environ.get("ZOHO_CLIENT_SECRET", "").strip()
    refresh = os.environ.get("ZOHO_REFRESH_TOKEN", "").strip()
    if not (cid and secret and refresh):
        raise RuntimeError("ZOHO_CLIENT_ID/SECRET/REFRESH_TOKEN required to refresh Zoho token")
    accounts = (os.environ.get("ZOHO_ACCOUNTS_BASE", "https://accounts.zoho.in")).rstrip("/")
    body = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "client_id": cid,
            "client_secret": secret,
            "refresh_token": refresh,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{accounts}/oauth/v2/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("Zoho OAuth refresh returned no access_token")
    return token


class Adapter:
    def __init__(self) -> None:
        self.token = os.environ.get("ZOHO_MAIL_ACCESS_TOKEN", "").strip()
        self.account_id = os.environ.get("ZOHO_MAIL_ACCOUNT_ID", "").strip()
        self.api_base = os.environ.get("ZOHO_MAIL_API_BASE", "https://mail.zoho.in/api").rstrip("/")
        self.from_addr = os.environ.get("ZOHO_MAIL_FROM", "").strip()

    def _ensure_token(self, *, force_refresh: bool = False) -> str:
        can_refresh = all(
            (os.environ.get(k) or "").strip()
            for k in ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN")
        )
        if force_refresh or (can_refresh and not self.token):
            self.token = _refresh_access_token()
            return self.token
        if can_refresh:
            self.token = _refresh_access_token()
            return self.token
        if self.token:
            return self.token
        raise RuntimeError("Zoho mail credentials not configured")

    @property
    def available(self) -> bool:
        has_refresh = all(
            (os.environ.get(k) or "").strip()
            for k in ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN")
        )
        return bool(self.account_id and self.from_addr and (self.token or has_refresh))

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        _ = read_only
        if operation != "message.send":
            raise ValueError(operation)
        if not self.available:
            raise RuntimeError("Zoho mail credentials not configured")
        payload = {
            "fromAddress": self.from_addr,
            "toAddress": ",".join(params.get("to") or []),
            "ccAddress": ",".join(params.get("cc") or []),
            "subject": params.get("subject") or "",
            "content": params.get("html_body") or params.get("text_body") or "",
            "mailFormat": "html" if params.get("html_body") else "plaintext",
        }
        url = f"{self.api_base}/accounts/{self.account_id}/messages"

        def _post(token: str) -> str:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Zoho-oauthtoken {token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")

        token = self._ensure_token()
        try:
            raw = _post(token)
        except urllib.error.HTTPError as exc:
            if exc.code != 401:
                raise RuntimeError(f"Zoho mail send failed: {exc.code}") from exc
            token = self._ensure_token(force_refresh=True)
            try:
                raw = _post(token)
            except urllib.error.HTTPError as retry_exc:
                raise RuntimeError(f"Zoho mail send failed: {retry_exc.code}") from retry_exc
        return {"ok": True, "provider_status": raw[:500]}
