from __future__ import annotations

from typing import Any, Protocol


class CatalogStore(Protocol):
    """Procedural catalog (prompts/runbooks/spt) — read-only until promotion gate."""

    name: str

    def status(self) -> dict[str, Any]: ...

    def summary(self) -> dict[str, Any]: ...
