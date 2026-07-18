"""Zoho Calendar adapter — OAuth via refresh_token (preferred) or static access token."""

from __future__ import annotations

import json
import os
import uuid
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

from am_platform_adapters.providers.zoho.oauth import resolve_access_token


class ZohoCalendar:
    """
    Create event via Zoho Calendar API.

    Prefers ZOHO_CLIENT_ID / ZOHO_CLIENT_SECRET / ZOHO_REFRESH_TOKEN (auto-refresh).
    Falls back to ZOHO_CALENDAR_ACCESS_TOKEN. Use CALENDAR_PROVIDER=fake for lab without Zoho.
    """

    def __init__(self, access_token: str | None = None, calendar_uid: str | None = None) -> None:
        self._static_token = (
            access_token or os.environ.get("ZOHO_CALENDAR_ACCESS_TOKEN", "")
        ).strip()
        self._token = ""
        self._cal = (calendar_uid or os.environ.get("ZOHO_CALENDAR_UID", "")).strip()
        self._api = (os.environ.get("ZOHO_CALENDAR_API_BASE", "https://calendar.zoho.in/api/v1")).rstrip(
            "/"
        )

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

    def create_event(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
        attendees: list[str] | None = None,
        refs: dict[str, str] | None = None,
    ) -> str:
        if not self._cal:
            raise RuntimeError("ZOHO_CALENDAR_UID required (or CALENDAR_PROVIDER=fake)")
        refs = refs or {}
        payload: dict[str, Any] = {
            "title": title,
            "dateandtime": {
                "start": start.strftime("%Y%m%dT%H%M%S"),
                "end": end.strftime("%Y%m%dT%H%M%S"),
            },
            "attendees": [{"email": e} for e in (attendees or [])],
            "description": "\n".join(f"{k}={v}" for k, v in refs.items()),
        }
        url = f"{self._api}/calendars/{self._cal}/events"

        def _post(token: str) -> None:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Zoho-oauthtoken {token}",
                    "Content-Type": "application/json",
                    "User-Agent": "am-platform-adapters/0.1 (ZohoCalendar)",
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
                raise RuntimeError(f"Zoho Calendar create failed {exc.code}: {detail[:300]}") from exc
            token = self._ensure_token(force_refresh=True)
            try:
                _post(token)
            except urllib.error.HTTPError as retry_exc:
                detail = retry_exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"Zoho Calendar create failed {retry_exc.code}: {detail[:300]}"
                ) from retry_exc
        return f"zoho-cal-{uuid.uuid4().hex[:12]}"
