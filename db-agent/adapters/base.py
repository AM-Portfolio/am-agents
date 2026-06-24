from __future__ import annotations

from typing import Any, Protocol


class BaseAdapter(Protocol):
    @property
    def available(self) -> bool: ...

    async def execute(
        self, operation: str, params: dict[str, Any], *, read_only: bool, max_rows: int
    ) -> Any: ...
