from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Redactor(Protocol):
    def scrub(self, *, payload: Any) -> Any:
        """Strip secrets / sensitive fields before notify, docs, LLM, or traces."""
        ...
