"""Minimal Jira Cloud REST client (stdlib only)."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urljoin


class JiraError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.body = body


class JiraClient:
    """Basic auth: email + API token (Atlassian Cloud)."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("JIRA_BASE_URL", "")).rstrip("/") + "/"
        self.email = (email or os.environ.get("JIRA_EMAIL", "")).strip()
        self.api_token = (api_token or os.environ.get("JIRA_API_TOKEN", "")).strip()
        self.timeout = timeout
        if not self.base_url.strip("/") or not self.email or not self.api_token:
            raise RuntimeError("JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN required")

    def _headers(self) -> dict[str, str]:
        raw = f"{self.email}:{self.api_token}".encode()
        auth = base64.b64encode(raw).decode("ascii")
        return {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "am-platform-adapters/0.1 (Jira)",
        }

    def request(self, method: str, path: str, *, body: dict[str, Any] | None = None) -> dict[str, Any]:
        url = urljoin(self.base_url, path.lstrip("/"))
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(), method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise JiraError(
                f"Jira {method.upper()} {path} failed {exc.code}: {detail[:400]}",
                status=exc.code,
                body=detail,
            ) from exc

    def get(self, path: str) -> dict[str, Any]:
        return self.request("GET", path)

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", path, body=body)

    def put(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return self.request("PUT", path, body=body)
