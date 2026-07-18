from __future__ import annotations

from typing import Any


class MemoryAdapter:
    @property
    def available(self) -> bool:
        return True

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        _ = read_only
        kind = operation.split(".", 1)[0]
        return {
            "kind": kind,
            "query_ref": params.get("query_ref") or params.get("query") or "",
            "status": "ok",
            "summary": f"memory {operation}",
            "points": [],
        }
