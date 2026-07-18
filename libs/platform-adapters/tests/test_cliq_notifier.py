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


def test_card_payload_link_buttons() -> None:
    """In-chat open.url buttons (Cliq ⋮ popup for overflow) — no MinIO View more."""
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
                {"label": "OpenProject", "url": "https://openproject.asrax.in/work_packages/391"},
                {"label": "Open alert", "url": "https://grafana.asrax.in/alerting/x"},
                {"label": "Temporal", "url": "http://127.0.0.1:8080/wf"},
                {"label": "Langfuse", "url": "https://langfuse.munish.org"},
            ],
        },
    )
    payload = _card_to_cliq_payload(card)
    assert set(payload.keys()) - {"_plain"} == {"text", "card", "slides", "buttons"}
    assert len(payload["buttons"]) == 4
    assert all(b["action"]["type"] == "open.url" for b in payload["buttons"])
    assert payload["buttons"][0]["label"] == "OpenProject"
    assert "url" not in payload["buttons"][0]["action"]["data"]  # only web key


def test_plain_fallback_is_human() -> None:
    card = NotifyCard(
        event="incident.resolved",
        title="✅ RESOLVED · WARNING · KubeServiceDown",
        body="redis down",
        refs={"ticket": "390", "env": "lab", "status": "RESOLVED"},
        meta={"buttons": [{"label": "OpenProject", "url": "https://openproject.asrax.in/work_packages/390"}]},
    )
    plain = _plain_fallback(card)
    assert "Ticket: 390" in plain
    assert "OpenProject:" in plain
