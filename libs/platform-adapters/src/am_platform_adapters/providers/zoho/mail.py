"""Zoho Mail adapter — OAuth token from env (lab stub until vault wired)."""

from __future__ import annotations

import json
import os
import uuid
import urllib.error
import urllib.request
from typing import Any


class ZohoMail:
    """
    POST message via Zoho Mail API when ZOHO_MAIL_ACCESS_TOKEN is set.
    Without token, raises RuntimeError (use MAIL_PROVIDER=fake for lab).
    """

    def __init__(self, access_token: str | None = None, account_id: str | None = None) -> None:
        self._token = (access_token or os.environ.get("ZOHO_MAIL_ACCESS_TOKEN", "")).strip()
        self._account = (account_id or os.environ.get("ZOHO_MAIL_ACCOUNT_ID", "")).strip()
        self._api = (os.environ.get("ZOHO_MAIL_API_BASE", "https://mail.zoho.in/api")).rstrip("/")

    def send(
        self,
        *,
        to: list[str],
        subject: str,
        body: str,
        refs: dict[str, str] | None = None,
    ) -> str:
        if not self._token or not self._account:
            raise RuntimeError(
                "ZOHO_MAIL_ACCESS_TOKEN and ZOHO_MAIL_ACCOUNT_ID required (or MAIL_PROVIDER=fake)"
            )
        refs = refs or {}
        payload: dict[str, Any] = {
            "fromAddress": os.environ.get("ZOHO_MAIL_FROM", ""),
            "toAddress": ",".join(to),
            "subject": subject,
            "content": body + ("\n\n" + "\n".join(f"{k}={v}" for k, v in refs.items()) if refs else ""),
        }
        url = f"{self._api}/accounts/{self._account}/messages"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Zoho-oauthtoken {self._token}",
                "Content-Type": "application/json",
                "User-Agent": "am-platform-adapters/0.1 (ZohoMail)",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Zoho Mail send failed {exc.code}: {detail[:300]}") from exc
        return f"zoho-mail-{uuid.uuid4().hex[:12]}"
