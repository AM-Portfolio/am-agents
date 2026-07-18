"""CalendarPort — schedule events (opaque event_ref)."""

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class CalendarPort(Protocol):
    def create_event(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
        attendees: list[str] | None = None,
        refs: dict[str, str] | None = None,
    ) -> str:
        """Return opaque event_ref."""
        ...
