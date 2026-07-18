"""Zoho Cliq Notifier adapter — compact modern-inline cards for channel webhooks."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
import uuid
from typing import Any

from am_platform_ports.schemas.core import NotifyCard

LOG = logging.getLogger("am_platform_adapters.cliq")


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
    if ref.startswith("https://"):
        return channel_ref.strip()
    return os.environ.get("ZOHO_CLIQ_WEBHOOK_URL", "").strip()


def _plain_fallback(card: NotifyCard) -> str:
    """Last-resort plain text — keep human, never key=value dumps."""
    refs = card.refs or {}
    lines = [(card.title or "").strip(), (card.body or "").strip()]
    bits = []
    if refs.get("ticket"):
        bits.append(f"Ticket: {refs['ticket']}")
    if refs.get("env"):
        bits.append(f"Env: {refs['env']}")
    if refs.get("status"):
        bits.append(f"Status: {refs['status']}")
    if bits:
        lines.append(" · ".join(bits))
    meta = card.meta or {}
    buttons = meta.get("buttons") if isinstance(meta.get("buttons"), list) else []
    for b in buttons[:4]:
        if isinstance(b, dict) and b.get("url") and b.get("label"):
            lines.append(f"• {b['label']}: {b['url']}")
    return "\n".join(p for p in lines if p)[:3500]


def _card_to_cliq_payload(card: NotifyCard) -> dict[str, Any]:
    """
    Channel incoming webhooks (zapikey) accept only: text, card, slides.
    They reject top-level `buttons` and often `bot` with extra_key_found.
    Put links in a list slide instead of buttons.
    """
    from am_platform_ports.agent_identity import agent_display_name

    refs = {k: str(v) for k, v in (card.refs or {}).items() if v and str(v) != "unavailable"}
    meta = card.meta or {}
    buttons = meta.get("buttons") if isinstance(meta.get("buttons"), list) else []
    title = (card.title or "Incident").strip()[:100]
    status = refs.get("status") or ""
    headline = f"{status} · {title}"[:120] if status and status not in title else title

    label_data: dict[str, str] = {}
    for key, label in (
        ("status", "Status"),
        ("ticket", "Ticket"),
        ("env", "Env"),
        ("done_by", "Done by"),
        ("responsible", "Responsible"),
        ("alert_id", "Alert ID"),
    ):
        if refs.get(key):
            label_data[label] = refs[key][:120]
    if "Done by" not in label_data:
        label_data["Done by"] = agent_display_name()

    slides: list[dict[str, Any]] = []
    if label_data:
        slides.append({"type": "label", "data": [label_data]})
    body = (card.body or "").strip()
    if body:
        slides.append({"type": "text", "title": "Update", "data": body[:1500]})

    link_lines: list[str] = []
    for b in buttons[:4]:
        if not isinstance(b, dict):
            continue
        label = str(b.get("label") or "").strip()
        url = str(b.get("url") or "").strip()
        if label and url.startswith("http"):
            link_lines.append(f"{label}: {url}")
    if link_lines:
        slides.append({"type": "list", "title": "Links", "data": link_lines})

    # Channel webhook schema: text + card + slides only (no buttons / bot)
    payload: dict[str, Any] = {
        "text": headline,
        "card": {
            "title": title,
            "theme": str(meta.get("theme") or "modern-inline"),
        },
    }
    if slides:
        payload["slides"] = slides
    payload["_plain"] = _plain_fallback(card)
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
            detail = exc.read().decode("utf-8", errors="replace")
            LOG.warning("cliq rich card rejected code=%s detail=%s", exc.code, detail[:200])
            if exc.code >= 400:
                body2 = json.dumps({"text": plain}).encode("utf-8")
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
                        f"Cliq send failed {exc2.code}: {detail2[:300]} "
                        f"(rich also {exc.code}: {detail[:120]})"
                    ) from exc2
            else:
                raise RuntimeError(f"Cliq send failed {exc.code}: {detail[:300]}") from exc

        return f"cliq-{uuid.uuid4().hex[:12]}"
