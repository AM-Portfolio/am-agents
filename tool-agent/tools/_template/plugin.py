from __future__ import annotations

from pathlib import Path

from app.models.intent import IntentDocument
from tools._base_plugin import BaseIntegrationTool
from tools._template.search import parse_rules, resolve
from tools._template import safety


class TemplateTool(BaseIntegrationTool):
    def parse_rules(self, query: str, backend_hint: str | None) -> IntentDocument | None:
        if backend_hint and backend_hint != self.name:
            return None
        return parse_rules.parse_rules(query, tool_name=self.name)

    def resolve(self, intent: IntentDocument, query: str) -> tuple[IntentDocument, str | None]:
        return resolve.resolve(intent, query)

    def validate_safety(self, intent: IntentDocument, *, request_read_only: bool) -> None:
        safety.validate(intent, request_read_only=request_read_only)


def get_tool() -> TemplateTool:
    return TemplateTool(Path(__file__).resolve().parent)
