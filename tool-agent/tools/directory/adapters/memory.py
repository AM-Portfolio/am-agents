from __future__ import annotations

from typing import Any


class MemoryAdapter:
    @property
    def available(self) -> bool:
        return True

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        _ = read_only
        if operation != "owner.resolve":
            raise ValueError(operation)
        service = str(params.get("service") or params.get("team") or "default")
        return {
            "assignee_ref": f"mem:user:{service}",
            "assignee_name": f"{service}-owner",
            "assignee_email": f"{service}@example.com",
            "channel_ref": "cliq:lab",
            "owner_source": "memory",
        }
