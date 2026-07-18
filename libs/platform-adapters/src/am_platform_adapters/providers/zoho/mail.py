"""Zoho Mail adapter — OAuth via refresh_token (preferred) or static access token."""

from __future__ import annotations

import json
import os
import uuid
import urllib.error
import urllib.request
from typing import Any

from am_platform_adapters.providers.zoho.oauth import resolve_access_token


class ZohoMail:
    """
    POST message via Zoho Mail API.

    Prefers ZOHO_CLIENT_ID / ZOHO_CLIENT_SECRET / ZOHO_REFRESH_TOKEN (auto-refresh).
    Falls back to ZOHO_MAIL_ACCESS_TOKEN. Use MAIL_PROVIDER=fake for lab without Zoho.
    """

    def __init__(self, access_token: str | None = None, account_id: str | None = None) -> None:
        self._static_token = (access_token or os.environ.get("ZOHO_MAIL_ACCESS_TOKEN", "")).strip()
        self._token = ""
        self._account = (account_id or os.environ.get("ZOHO_MAIL_ACCOUNT_ID", "")).strip()
        self._api = (os.environ.get("ZOHO_MAIL_API_BASE", "https://mail.zoho.in/api")).rstrip("/")
        self._from = (os.environ.get("ZOHO_MAIL_FROM", "")).strip()

    def _ensure_token(self, *, force_refresh: bool = False) -> str:
        if self._token and not force_refresh:
            return self._token
        self._token = resolve_access_token(
            static_token=self._static_token,
            prefer_refresh=force_refresh
            or bool(
                (os.environ.get("ZOHO_CLIENT_ID") or "").strip()
                and (os.environ.get("ZOHO_REFRESH_TOKEN") or "").strip()
            ),
        )
        return self._token

    def send(
        self,
        *,
        to: list[str],
        subject: str,
        body: str,
        refs: dict[str, str] | None = None,
        html_body: str | None = None,
    ) -> str:
        if not self._account:
            raise RuntimeError("ZOHO_MAIL_ACCOUNT_ID required (or MAIL_PROVIDER=fake)")
        refs = refs or {}
        content = html_body or body
        if refs and not html_body:
            content = content + ("\n\n" + "\n".join(f"{k}={v}" for k, v in refs.items()))
        payload: dict[str, Any] = {
            "fromAddress": self._from,
            "toAddress": ",".join(to),
            "subject": subject,
            "content": content,
            "mailFormat": "html" if html_body else "plaintext",
        }
        url = f"{self._api}/accounts/{self._account}/messages"

        def _post(token: str) -> None:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Zoho-oauthtoken {token}",
                    "Content-Type": "application/json",
                    "User-Agent": "am-platform-adapters/0.1 (ZohoMail)",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp.read()

        token = self._ensure_token()
        try:
            _post(token)
        except urllib.error.HTTPError as exc:
            if exc.code != 401:
                detail = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"Zoho Mail send failed {exc.code}: {detail[:300]}") from exc
            token = self._ensure_token(force_refresh=True)
            try:
                _post(token)
            except urllib.error.HTTPError as retry_exc:
                detail = retry_exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"Zoho Mail send failed {retry_exc.code}: {detail[:300]}"
                ) from retry_exc
        return f"zoho-mail-{uuid.uuid4().hex[:12]}"
