"""DocStore — opaque document refs (MinIO primary / GDrive failover)."""

from typing import Protocol, runtime_checkable

from am_platform_ports.schemas.core import DocRef


@runtime_checkable
class DocStore(Protocol):
    def put(
        self,
        *,
        key: str,
        content: bytes,
        content_type: str = "application/octet-stream",
        meta: dict[str, str] | None = None,
    ) -> DocRef:
        """Store bytes; return opaque docs_ref that sticks to the provider used."""
        ...

    def get(self, *, docs_ref: str) -> bytes: ...

    def exists(self, *, docs_ref: str) -> bool: ...
