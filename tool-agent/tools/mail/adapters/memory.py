from __future__ import annotations

from typing import Any


class MemoryAdapter:
    sent: list[dict[str, Any]] = []

    @property
    def available(self) -> bool:
        return True

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        _ = read_only
        if operation != "message.send":
            raise ValueError(operation)
        self.sent.append(dict(params))
        return {"mail_ref": f"mem:mail:{len(self.sent)}", "to": list(params.get("to") or [])}
