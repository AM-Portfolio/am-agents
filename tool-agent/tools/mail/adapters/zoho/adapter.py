from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


class Adapter:
    def __init__(self) -> None:
        self.token = os.environ.get("ZOHO_MAIL_ACCESS_TOKEN", "").strip()
        self.account_id = os.environ.get("ZOHO_MAIL_ACCOUNT_ID", "").strip()
        self.api_base = os.environ.get("ZOHO_MAIL_API_BASE", "https://mail.zoho.com/api").rstrip("/")
        self.from_addr = os.environ.get("ZOHO_MAIL_FROM", "").strip()

    @property
    def available(self) -> bool:
        return bool(self.token and self.account_id and self.from_addr)

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
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Zoho-oauthtoken {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Zoho mail send failed: {exc.code}") from exc
        return {"ok": True, "provider_status": raw[:500]}
