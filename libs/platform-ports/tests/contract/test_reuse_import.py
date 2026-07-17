"""Prove another path can import TicketStore from am_platform_ports only."""

from am_platform_ports.fakes import FakeTicketStore
from am_platform_ports.ports.ticket import TicketStore


def test_reuse_import() -> None:
    store: TicketStore = FakeTicketStore()
    ref = store.create(title="reuse", description="from other agent", priority="P3")
    assert ref.ticket_ref
