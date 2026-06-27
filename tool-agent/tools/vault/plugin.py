from __future__ import annotations

from pathlib import Path
from typing import Any

from app.models.intent import IntentDocument
from tools._base_plugin import BaseIntegrationTool
from tools.vault.adapter import VaultMcpAdapter
from tools.vault.safety import validate as validate_vault_safety
from tools.vault.safety import validate_tool_params as validate_vault_tool_params
from tools.vault.search import parse_rules, resolve


class VaultTool(BaseIntegrationTool):
    def __init__(self, tool_dir: Path) -> None:
        super().__init__(tool_dir)
        self._adapter = VaultMcpAdapter()

    def parse_rules(self, query: str, backend_hint: str | None) -> IntentDocument | None:
        return parse_rules.parse_rules(query, tool_name=self.name, backend_hint=backend_hint)

    def resolve(self, intent: IntentDocument, query: str) -> tuple[IntentDocument, str | None]:
        return resolve.resolve(intent, query)

    def validate_safety(self, intent: IntentDocument, *, request_read_only: bool) -> None:
        validate_vault_safety(intent, request_read_only=request_read_only, is_execute_path=False)

    def adapter_available(self) -> bool:
        return self._adapter.available

    async def execute(self, intent: IntentDocument, *, read_only: bool, max_rows: int) -> Any:
        validate_vault_tool_params(intent.operation, intent.params)
        return await self._adapter.execute(
            intent.operation,
            intent.params,
            read_only=read_only,
            max_rows=max_rows,
        )


def get_tool() -> VaultTool:
    return VaultTool(Path(__file__).resolve().parent)
