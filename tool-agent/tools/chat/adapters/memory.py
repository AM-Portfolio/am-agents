from __future__ import annotations

from typing import Any


class MemoryAdapter:
    sent: list[dict[str, Any]] = []

    @property
    def available(self) -> bool:
        return True

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        _ = read_only
        payload = {"operation": operation, **params}
        self.sent.append(payload)
        return {"message_ref": f"mem:chat:{len(self.sent)}", "channel_ref": params.get("channel_ref") or ""}
