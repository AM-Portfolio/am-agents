from typing import Protocol, runtime_checkable


@runtime_checkable
class PolicyPort(Protocol):
    def allow(self, *, action: str, context: dict) -> bool: ...
