"""Cliq notifier unit tests (no network)."""

from am_platform_adapters.providers.cliq.notifier import _card_to_cliq_payload, _webhook_for_channel
from am_platform_ports.schemas.core import NotifyCard


def test_webhook_lab_uses_lab_env(monkeypatch) -> None:
    monkeypatch.setenv("ZOHO_CLIQ_LAB_WEBHOOK_URL", "https://example.test/lab")
    monkeypatch.setenv("ZOHO_CLIQ_WEBHOOK_URL", "https://example.test/main")
    assert _webhook_for_channel("cliq:lab") == "https://example.test/lab"


def test_card_payload_has_title_and_refs() -> None:
    card = NotifyCard(
        event="ticket.created",
        title="[P2] smoke",
        body="Ticket created",
        refs={"ticket_ref": "ticket-1", "run_ref": "run-1"},
    )
    payload = _card_to_cliq_payload(card)
    assert payload["text"] == "[P2] smoke"
    assert "slides" in payload
