from typing import Protocol, runtime_checkable

from am_platform_ports.schemas.core import NotifyCard


@runtime_checkable
class Notifier(Protocol):
    def send_card(self, *, channel_ref: str, card: NotifyCard) -> str:
        """Return opaque notify_ref. Follow-up cards only (no edit API v1)."""
        ...
