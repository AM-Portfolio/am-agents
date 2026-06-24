from __future__ import annotations

from pathlib import Path
from typing import Any

from app.models.intent import IntentDocument
from tools._base_plugin import BaseIntegrationTool
from tools.redis import safety
from tools.redis.adapter import RedisAdapter
from tools.redis.search import parse_rules, resolve


class RedisTool(BaseIntegrationTool):
    def __init__(self, tool_dir: Path) -> None:
        super().__init__(tool_dir)
        self._adapter = RedisAdapter()

    def parse_rules(self, query: str, backend_hint: str | None) -> IntentDocument | None:
        if backend_hint and backend_hint != self.name:
            return None
        return parse_rules.parse_rules(query, tool_name=self.name)

    def resolve(self, intent: IntentDocument, query: str) -> tuple[IntentDocument, str | None]:
        return resolve.resolve(intent, query)

    def validate_safety(self, intent: IntentDocument, *, request_read_only: bool) -> None:
        safety.validate(intent, request_read_only=request_read_only)

    def adapter_available(self) -> bool:
        return self._adapter.available

    async def execute(self, intent: IntentDocument, *, read_only: bool, max_rows: int) -> Any:
        return await self._adapter.execute(
            intent.operation,
            intent.params,
            read_only=read_only,
            max_rows=max_rows,
        )


def get_tool() -> RedisTool:
    return RedisTool(Path(__file__).resolve().parent)
