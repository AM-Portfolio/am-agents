from typing import Protocol, runtime_checkable

from am_platform_ports.schemas.core import TicketRef


@runtime_checkable
class TicketStore(Protocol):
    def create(self, *, title: str, description: str, priority: str, labels: dict[str, str] | None = None) -> TicketRef: ...

    def assign(self, *, ticket_ref: str, assignee_ref: str) -> None: ...

    def comment(self, *, ticket_ref: str, body: str) -> None: ...

    def update_status(self, *, ticket_ref: str, status: str) -> None: ...
