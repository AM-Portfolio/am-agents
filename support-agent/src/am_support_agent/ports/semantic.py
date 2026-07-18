from __future__ import annotations

from typing import Any, Protocol


class SemanticIndex(Protocol):
    """Post-canary Qdrant stub — never authorizes actions."""

    name: str

    def status(self) -> dict[str, Any]: ...

    async def search(self, *, query: str, limit: int = 5) -> list[dict[str, Any]]: ...
