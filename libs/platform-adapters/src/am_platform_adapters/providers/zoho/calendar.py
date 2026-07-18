"""Zoho Calendar adapter — OAuth token from env (lab stub until vault wired)."""

from __future__ import annotations

import json
import os
import uuid
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any


class ZohoCalendar:
    """
    Create event via Zoho Calendar API when ZOHO_CALENDAR_ACCESS_TOKEN is set.
    Without token, raises RuntimeError (use CALENDAR_PROVIDER=fake for lab).
    """

    def __init__(self, access_token: str | None = None, calendar_uid: str | None = None) -> None:
        self._token = (access_token or os.environ.get("ZOHO_CALENDAR_ACCESS_TOKEN", "")).strip()
        self._cal = (calendar_uid or os.environ.get("ZOHO_CALENDAR_UID", "")).strip()
        self._api = (os.environ.get("ZOHO_CALENDAR_API_BASE", "https://calendar.zoho.in/api/v1")).rstrip(
            "/"
        )

    def create_event(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
        attendees: list[str] | None = None,
        refs: dict[str, str] | None = None,
    ) -> str:
        if not self._token or not self._cal:
            raise RuntimeError(
                "ZOHO_CALENDAR_ACCESS_TOKEN and ZOHO_CALENDAR_UID required (or CALENDAR_PROVIDER=fake)"
            )
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
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Zoho-oauthtoken {self._token}",
                "Content-Type": "application/json",
                "User-Agent": "am-platform-adapters/0.1 (ZohoCalendar)",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Zoho Calendar create failed {exc.code}: {detail[:300]}") from exc
        return f"zoho-cal-{uuid.uuid4().hex[:12]}"
