from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from app.models.intent import IntentDocument


@dataclass
class PromptRef:
    source: str = "file"
    name: str = ""
    label: str = "{{APP_ENV}}"
    fallback: str = "prompts/intent.yaml"
    optional: bool = False


@dataclass
class ToolManifest:
    name: str
    display_name: str = ""
    enabled: bool = True
    version: str = "1.0.0"
    infer_keywords: list[str] = field(default_factory=list)
    vault_path_template: str | None = None
    env_prefix: str = ""
    supports_mcp: bool = False
    mcp_server: str | None = None
    has_entities: bool = False
    health_check: str = "skip"
    prompts: dict[str, PromptRef] = field(default_factory=dict)


@runtime_checkable
class IntegrationTool(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def manifest(self) -> ToolManifest: ...

    @property
    def tool_dir(self) -> Path: ...

    def is_enabled(self) -> bool: ...

    def registry_entry(self) -> dict[str, Any]: ...

    def operations(self) -> list[str]: ...

    def parse_rules(self, query: str, backend_hint: str | None) -> IntentDocument | None: ...

    def resolve(self, intent: IntentDocument, query: str) -> tuple[IntentDocument, str | None]: ...

    def infer_keywords(self) -> list[str]: ...

    def validate_intent(self, intent: IntentDocument) -> None: ...

    def validate_safety(self, intent: IntentDocument, *, request_read_only: bool) -> None: ...

    def adapter_available(self) -> bool: ...

    async def execute(
        self,
        intent: IntentDocument,
        *,
        read_only: bool,
        max_rows: int,
    ) -> Any: ...
