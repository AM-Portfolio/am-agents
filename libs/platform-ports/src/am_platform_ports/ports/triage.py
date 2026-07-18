from typing import Protocol, runtime_checkable

from am_platform_ports.schemas.core import TriageResult


@runtime_checkable
class TriagePort(Protocol):
    def classify(self, *, alert_payload: dict) -> TriageResult: ...
