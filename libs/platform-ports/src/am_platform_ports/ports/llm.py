from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LlmPort(Protocol):
    def complete(self, *, prompt_key: str, variables: dict[str, Any], data_class: str = "internal") -> str:
        """Gateway-only LLM access. Never pass env or secret values."""
        ...
