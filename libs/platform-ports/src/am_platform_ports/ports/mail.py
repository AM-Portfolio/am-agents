"""MailPort — send follow-up / summary email (opaque mail_ref)."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class MailPort(Protocol):
    def send(
        self,
        *,
        to: list[str],
        subject: str,
        body: str,
        refs: dict[str, str] | None = None,
    ) -> str:
        """Return opaque mail_ref."""
        ...
