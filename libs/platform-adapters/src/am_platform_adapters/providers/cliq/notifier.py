"""Zoho Cliq Notifier — obs-platform style cards (table + open.url buttons)."""

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


def _cliq_button(label: str, url: str, tone: str = "+", *, action: str = "open.url") -> dict[str, Any]:
    """Zoho open.url button — opens in browser; Cliq keeps buttons in-chat (⋮ overflow popup)."""
    return {
        "label": (label or "Open")[:30],
        "type": tone,
        "action": {"type": "open.url", "data": {"web": url[:256]}},
    }



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
    Match am-obs-platform alert cards:
      text + card(modern-inline) + one table slide + top-level buttons(open.url).

    Full detail: Summary/Update/timing on the card; links as open.url buttons
    (Cliq ⋮ menu is the in-chat popup for overflow — same as original FIRING cards).
    """
    meta = card.meta or {}
    title = (card.title or "Incident").strip()[:100]
    mention = str(meta.get("mention") or "\u200b")

    table_rows = meta.get("table_rows") if isinstance(meta.get("table_rows"), list) else []
    if not table_rows:
        # Backward-compatible fallback from body/refs
        refs = {k: str(v) for k, v in (card.refs or {}).items() if v}
        body = (card.body or "").strip()
        for field, value in (
            ("Summary", body[:120] if body else ""),
            ("Where", f"env={refs['env']}" if refs.get("env") else ""),
            ("IDs", refs.get("alert_id") or ""),
        ):
            if value:
                table_rows.append({"Field": field, "Value": value})

    slides: list[dict[str, Any]] = []
    if table_rows:
        slides.append(
            {
                "type": "table",
                "data": {"headers": ["Field", "Value"], "rows": table_rows[:10]},
            }
        )

    raw_buttons = meta.get("buttons") if isinstance(meta.get("buttons"), list) else []
    buttons: list[dict[str, Any]] = []
    for b in raw_buttons[:4]:
        if not isinstance(b, dict):
            continue
        label = str(b.get("label") or "").strip()
        url = str(b.get("url") or "").strip()
        if label and url.startswith("http"):
            buttons.append(_cliq_button(label, url))

    # Same shape as obs-platform _to_cliq_message
    payload: dict[str, Any] = {
        "text": mention[:1500],
        "card": {
            "theme": str(meta.get("theme") or "modern-inline"),
            "title": title[:200],
        },
    }
    if slides:
        payload["slides"] = slides
    if buttons:
        payload["buttons"] = buttons
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
                # preview.url may be rejected on channel webhooks — retry as open.url
                if "buttons" in payload and any(
                    isinstance(b, dict) and (b.get("action") or {}).get("type") == "preview.url"
                    for b in payload.get("buttons") or []
                ):
                    open_payload = dict(payload)
                    open_buttons = []
                    for b in payload.get("buttons") or []:
                        if not isinstance(b, dict):
                            continue
                        web = ((b.get("action") or {}).get("data") or {}).get("web") or ""
                        if web:
                            open_buttons.append(_cliq_button(str(b.get("label") or "View more"), web))
                    open_payload["buttons"] = open_buttons
                    try:
                        req_o = urllib.request.Request(
                            url,
                            data=json.dumps(open_payload).encode("utf-8"),
                            headers={
                                "Content-Type": "application/json",
                                "User-Agent": "am-platform-adapters/0.1 (CliqNotifier)",
                            },
                            method="POST",
                        )
                        with urllib.request.urlopen(req_o, timeout=15) as resp_o:
                            resp_o.read()
                        return f"cliq-{uuid.uuid4().hex[:12]}"
                    except urllib.error.HTTPError as exc_o:
                        detail = exc_o.read().decode("utf-8", errors="replace")
                        LOG.warning("cliq open.url retry rejected code=%s detail=%s", exc_o.code, detail[:200])

                # Retry without buttons if channel rejects them; keep table card
                if "buttons" in payload:
                    slim = {k: v for k, v in payload.items() if k != "buttons"}
                    try:
                        req_s = urllib.request.Request(
                            url,
                            data=json.dumps(slim).encode("utf-8"),
                            headers={
                                "Content-Type": "application/json",
                                "User-Agent": "am-platform-adapters/0.1 (CliqNotifier)",
                            },
                            method="POST",
                        )
                        with urllib.request.urlopen(req_s, timeout=15) as resp_s:
                            resp_s.read()
                        return f"cliq-{uuid.uuid4().hex[:12]}"
                    except urllib.error.HTTPError:
                        pass
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
