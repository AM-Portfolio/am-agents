"""Catalog + semantic index adapters."""

from __future__ import annotations

from typing import Any

from am_support_agent.intelligence.catalog import CatalogReader


class FileCatalogStore:
    name = "file-catalog"

    def __init__(self, reader: CatalogReader | None = None) -> None:
        self._reader = reader or CatalogReader.from_env()

    def status(self) -> dict[str, Any]:
        summary = self._reader.summary()
        return {
            "name": self.name,
            "wired": True,
            "available": summary.get("available"),
            "root": summary.get("root"),
        }

    def summary(self) -> dict[str, Any]:
        return self._reader.summary()


class StubSemanticIndex:
    """Post-canary placeholder — never returns actionable authority."""

    name = "semantic-stub"

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "wired": False,
            "deferred": True,
            "note": "Qdrant semantic index is post-canary; Postgres episode filters are primary",
        }

    async def search(self, *, query: str, limit: int = 5) -> list[dict[str, Any]]:
        _ = query, limit
        return []
