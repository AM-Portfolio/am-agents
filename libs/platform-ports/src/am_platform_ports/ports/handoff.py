"""HandoffPort — transfer work between agent kinds (max depth 1)."""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class HandoffPort(Protocol):
    MAX_DEPTH: int = 1

    def handoff(
        self,
        *,
        from_run_ref: str,
        to_kind: str,
        depth: int,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Create a child handoff run. Raise if depth > MAX_DEPTH. Return new run_ref."""
        ...
