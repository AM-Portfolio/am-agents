from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def _webhook_for_channel(channel_ref: str) -> str:
    ref = (channel_ref or "").strip().lower()
    if ref in {"cliq:lab", "lab"}:
        return os.environ.get("ZOHO_CLIQ_LAB_WEBHOOK_URL", "").strip() or os.environ.get("ZOHO_CLIQ_WEBHOOK_URL", "").strip()
    if ref in {"cliq:prod", "prod"}:
        return os.environ.get("ZOHO_CLIQ_PROD_WEBHOOK_URL", "").strip() or os.environ.get("ZOHO_CLIQ_WEBHOOK_URL", "").strip()
    if ref.startswith("https://"):
        return channel_ref.strip()
    return os.environ.get("ZOHO_CLIQ_WEBHOOK_URL", "").strip()


class Adapter:
    @property
    def available(self) -> bool:
        return bool(os.environ.get("ZOHO_CLIQ_WEBHOOK_URL") or os.environ.get("ZOHO_CLIQ_LAB_WEBHOOK_URL"))

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        _ = read_only
        url = _webhook_for_channel(str(params.get("channel_ref") or ""))
        if not url:
            raise RuntimeError("Cliq webhook URL not configured")
        if operation == "message.send":
            body = {"text": str(params.get("body") or "")[:3500]}
        elif operation == "card.send":
            card = params.get("card") if isinstance(params.get("card"), dict) else {}
            body = {
                "text": str(params.get("body") or card.get("body") or "")[:3500],
                "card": {"title": str(card.get("title") or "Notification")[:100], "theme": "modern-inline"},
            }
        else:
            raise ValueError(f"unknown operation {operation}")
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Cliq send failed: {exc.code}") from exc
        return {"ok": True, "provider_status": raw[:500], "channel_ref": params.get("channel_ref") or ""}
