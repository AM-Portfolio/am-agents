from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class PromptRegistry(Protocol):
    def get(self, *, prompt_key: str, version: str | None = None) -> dict[str, Any]:
        """Return prompt content from catalog — never Python string literals."""
        ...
