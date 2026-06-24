from __future__ import annotations


class Adapter:
    @property
    def available(self) -> bool:
        return False

    async def ping(self, params: dict, *, read_only: bool, max_rows: int) -> dict:
        return {"status": "ok"}
