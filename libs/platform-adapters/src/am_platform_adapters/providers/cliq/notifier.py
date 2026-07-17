"""Zoho Cliq Notifier adapter — follow-up cards only (ADR design)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from typing import Any

from am_platform_ports.schemas.core import NotifyCard


def _webhook_for_channel(channel_ref: str) -> str:
    ref = (channel_ref or "").strip().lower()
    if ref in {"cliq:lab", "lab", "opslab"}:
        return (
            os.environ.get("ZOHO_CLIQ_LAB_WEBHOOK_URL", "").strip()
            or os.environ.get("ZOHO_CLIQ_WEBHOOK_URL", "").strip()
        )
    if ref in {"cliq:prod", "prod", "amalretsdev"}:
        return (
            os.environ.get("ZOHO_CLIQ_PROD_WEBHOOK_URL", "").strip()
            or os.environ.get("ZOHO_CLIQ_WEBHOOK_URL", "").strip()
        )
    if ref in {"cliq:summary", "summary", "devsupport"}:
        return os.environ.get("ZOHO_CLIQ_SUMMARY_WEBHOOK_URL", "").strip()
    # Opaque channel_ref may itself be a webhook URL (rare; prefer env)
    if ref.startswith("https://"):
        return channel_ref.strip()
    return os.environ.get("ZOHO_CLIQ_WEBHOOK_URL", "").strip()


def _stamp_title(card: NotifyCard) -> str:
    from am_platform_ports.agent_identity import agent_display_name, agent_prefix

    refs = card.refs or {}
    env = str(refs.get("env") or "").strip() or None
    decision = str(refs.get("decision") or card.event or "").strip() or None
    name = agent_display_name()
    title = (card.title or "").strip()
    if title.startswith("[") and name in title[:80]:
        return title
    return f"{agent_prefix(env=env, decision=decision)} {title}".strip()


def _card_to_cliq_payload(card: NotifyCard) -> dict[str, Any]:
    """Compact follow-up card — title + body + refs table."""
    refs = card.refs or {}
    title = _stamp_title(card)
    rows = [{"Field": k, "Value": str(v)} for k, v in refs.items() if v]
    slides: list[dict[str, Any]] = []
    if card.body:
        slides.append({"type": "text", "title": "", "data": card.body})
    if rows:
        slides.append(
            {
                "type": "table",
                "title": "Refs",
                "data": {"headers": ["Field", "Value"], "rows": rows},
            }
        )
    payload: dict[str, Any] = {
        "text": title,
        "card": {
            "title": title[:100],
            "theme": "modern-inline",
        },
    }
    if slides:
        payload["slides"] = slides
    # Fallback plain text if Cliq rejects rich cards
    payload["_plain"] = f"{title}\n{card.body}\n" + "\n".join(
        f"{k}={v}" for k, v in refs.items()
    )
    return payload


class CliqNotifier:
    """POST follow-up message to Cliq channel webhook."""

    def __init__(self, default_webhook: str | None = None) -> None:
        self._default = (default_webhook or "").strip()

    def send_card(self, *, channel_ref: str, card: NotifyCard) -> str:
        url = _webhook_for_channel(channel_ref) or self._default
        if not url or url.startswith("http://127.0.0.1"):
            raise RuntimeError("Cliq webhook URL not configured (ZOHO_CLIQ_*_WEBHOOK_URL)")

        payload = _card_to_cliq_payload(card)
        plain = payload.pop("_plain", card.title)
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "am-platform-adapters/0.1 (CliqNotifier)",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp.read()
        except urllib.error.HTTPError as exc:
            # Retry as plain text card
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code >= 400:
                body2 = json.dumps({"text": plain[:3500]}).encode("utf-8")
                req2 = urllib.request.Request(
                    url,
                    data=body2,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "am-platform-adapters/0.1 (CliqNotifier)",
                    },
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req2, timeout=15) as resp2:
                        resp2.read()
                except urllib.error.HTTPError as exc2:
                    detail2 = exc2.read().decode("utf-8", errors="replace")
                    raise RuntimeError(
                        f"Cliq send failed {exc2.code}: {detail2[:300]} (rich also {exc.code}: {detail[:120]})"
                    ) from exc2
            else:
                raise RuntimeError(f"Cliq send failed {exc.code}: {detail[:300]}") from exc

        return f"cliq-{uuid.uuid4().hex[:12]}"
