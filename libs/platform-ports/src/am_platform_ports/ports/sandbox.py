from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ToolSandbox(Protocol):
    def run(self, *, tool_name: str, args: dict[str, Any], secret_refs: list[str] | None = None) -> dict[str, Any]:
        """Deny-by-default allowlisted tools; scrubbed env; redacted output."""
        ...
