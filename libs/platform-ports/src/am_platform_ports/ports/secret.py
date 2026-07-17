from typing import Protocol, runtime_checkable


@runtime_checkable
class SecretBroker(Protocol):
    def resolve(self, *, secret_ref: str) -> str:
        """Resolve secret material inside adapters only — never into LLM/Temporal payloads."""
        ...
