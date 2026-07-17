"""InfraOps — plan / execute allowlisted fixes via ToolSandbox."""

from typing import Any, Protocol, runtime_checkable

from am_platform_ports.schemas.core import InfraOpsPlan, WorkDoneResult


@runtime_checkable
class InfraOps(Protocol):
    def plan(self, *, incident_ref: str, context: dict[str, Any]) -> InfraOpsPlan:
        """Propose allowlisted fix actions only."""
        ...

    def execute(
        self,
        *,
        plan: InfraOpsPlan,
        secret_refs: list[str] | None = None,
    ) -> WorkDoneResult:
        """Run plan actions via ToolSandbox (deny unknown tools)."""
        ...
