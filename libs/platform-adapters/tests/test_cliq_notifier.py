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


def test_card_payload_view_more_preview() -> None:
    """Single View more button → preview.url (popup panel) with details page URL."""
    card = NotifyCard(
        event="incident.resolved",
        title="✅ RESOLVED · WARNING · KubeServiceDown",
        body="KubeServiceDown: redis in infra",
        refs={"ticket": "391", "status": "RESOLVED", "env": "lab"},
        meta={
            "theme": "modern-inline",
            "mention": "\u200b",
            "table_rows": [
                {"Field": "Summary", "Value": "KubeServiceDown: redis in infra"},
                {"Field": "Update", "Value": "Verification passed"},
                {"Field": "Where", "Value": "env=lab · ns=infra · app=redis"},
            ],
            "buttons": [
                {
                    "label": "View more",
                    "url": "https://example.test/incident-cliq/details.html",
                    "action": "preview.url",
                },
            ],
        },
    )
    payload = _card_to_cliq_payload(card)
    assert set(payload.keys()) - {"_plain"} == {"text", "card", "slides", "buttons"}
    assert len(payload["buttons"]) == 1
    assert payload["buttons"][0]["label"] == "View more"
    assert payload["buttons"][0]["action"]["type"] == "preview.url"
    assert payload["buttons"][0]["action"]["data"]["web"].endswith("details.html")


def test_plain_fallback_is_human() -> None:
    card = NotifyCard(
        event="incident.resolved",
        title="✅ RESOLVED · WARNING · KubeServiceDown",
        body="redis down",
        refs={"ticket": "390", "env": "lab", "status": "RESOLVED"},
        meta={"buttons": [{"label": "View more", "url": "https://openproject.asrax.in/work_packages/390"}]},
    )
    plain = _plain_fallback(card)
    assert "Ticket: 390" in plain
    assert "View more:" in plain
