from typing import Protocol, runtime_checkable

from am_platform_ports.schemas.core import DirectoryHit


@runtime_checkable
class DirectoryPort(Protocol):
    def resolve(self, *, labels: dict[str, str], priority: str) -> DirectoryHit: ...
