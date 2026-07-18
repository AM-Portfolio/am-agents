from __future__ import annotations

from typing import Any, Protocol

from am_support_agent.contracts.capabilities import DocumentRef


class DocumentStore(Protocol):
    name: str

    def status(self) -> dict[str, Any]: ...

    async def put(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> DocumentRef: ...

    async def get(self, *, object_key: str) -> bytes: ...

    async def exists(self, *, object_key: str) -> bool: ...
