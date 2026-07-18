"""Minimal OpenProject API v3 HTTP client (stdlib only)."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urljoin, urlparse


class OpenProjectError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.body = body


class OpenProjectClient:
    """Basic auth with API token: username ``apikey``, password = plaintext token."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_token: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("OPENPROJECT_URL", "")).rstrip("/") + "/"
        self.api_token = (api_token or os.environ.get("OPENPROJECT_API_TOKEN", "")).strip()
        self.timeout = timeout
        if not self.base_url.strip("/"):
            raise RuntimeError("OPENPROJECT_URL is required")
        if not self.api_token:
            raise RuntimeError("OPENPROJECT_API_TOKEN is required")

    def _headers(self) -> dict[str, str]:
        raw = f"apikey:{self.api_token}".encode()
        auth = base64.b64encode(raw).decode("ascii")
        headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "am-platform-adapters/0.1 (OpenProject)",
        }
        # In-cluster HTTP needs Host matching OPENPROJECT_HOST__NAME
        parsed = urlparse(self.base_url)
        if parsed.hostname and (
            parsed.hostname.endswith(".svc.cluster.local")
            or parsed.hostname in {"127.0.0.1", "localhost"}
        ):
            public = os.environ.get("OPENPROJECT_PUBLIC_HOST", "openproject.asrax.in").strip()
            headers["Host"] = public
            headers["X-Forwarded-Proto"] = "https"
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = urljoin(self.base_url, path.lstrip("/"))
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = self._headers()
        if extra_headers:
            headers.update(extra_headers)
        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                if not raw:
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise OpenProjectError(
                f"OpenProject {method.upper()} {path} failed {exc.code}: {detail[:400]}",
                status=exc.code,
                body=detail,
            ) from exc

    def get(self, path: str) -> dict[str, Any]:
        return self.request("GET", path)

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", path, body=body)

    def patch(self, path: str, body: dict[str, Any], *, lock_version: int) -> dict[str, Any]:
        payload = dict(body)
        payload["lockVersion"] = lock_version
        return self.request("PATCH", path, body=payload)
