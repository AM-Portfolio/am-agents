"""Cliq notifier unit tests (no network)."""

from am_platform_adapters.providers.cliq.notifier import (
    _card_to_cliq_payload,
    _plain_fallback,
    _webhook_for_channel,
)
from am_platform_ports.schemas.core import NotifyCard


def test_webhook_lab_uses_lab_env(monkeypatch) -> None:
    monkeypatch.setenv("ZOHO_CLIQ_LAB_WEBHOOK_URL", "https://example.test/lab")
    monkeypatch.setenv("ZOHO_CLIQ_WEBHOOK_URL", "https://example.test/main")
    assert _webhook_for_channel("cliq:lab") == "https://example.test/lab"


def test_card_payload_channel_webhook_schema() -> None:
    """Channel zapikey webhooks reject buttons/bot — only text+card+slides."""
    card = NotifyCard(
        event="incident.investigating",
        title="[AM-1] INVESTIGATING",
        body="Reason: Ticket created and assigned — investigation started.",
        refs={"ticket": "390", "status": "INVESTIGATING", "env": "lab", "done_by": "IT-Support-agent"},
        meta={
            "theme": "modern-inline",
            "buttons": [
                {"label": "Temporal", "url": "http://127.0.0.1:8080/wf"},
                {"label": "OpenProject", "url": "https://openproject.asrax.in/work_packages/390"},
            ],
        },
    )
    payload = _card_to_cliq_payload(card)
    assert set(payload.keys()) - {"_plain"} <= {"text", "card", "slides"}
    assert "buttons" not in payload
    assert "bot" not in payload
    assert payload["card"]["theme"] == "modern-inline"
    assert payload["card"]["title"] == "[AM-1] INVESTIGATING"
    assert payload["slides"][0]["type"] == "label"
    link_slide = [s for s in payload["slides"] if s.get("type") == "list"][0]
    assert any("OpenProject" in x for x in link_slide["data"])
    plain = payload["_plain"]
    assert "grafana_trace=unavailable" not in plain
    assert "alert_id=" not in plain


def test_plain_fallback_is_human() -> None:
    card = NotifyCard(
        event="incident.resolved",
        title="[AM-2] RESOLVED",
        body="Reason: verify passed",
        refs={"ticket": "390", "env": "lab", "status": "RESOLVED"},
        meta={"buttons": [{"label": "OpenProject", "url": "https://openproject.asrax.in/work_packages/390"}]},
    )
    plain = _plain_fallback(card)
    assert "Ticket: 390" in plain
    assert "OpenProject:" in plain
