from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.models.intent import IntentDocument, SafetyError
from tools._loader import load_manifest
from tools._protocol import ToolManifest


class BaseIntegrationTool:
    def __init__(self, tool_dir: Path) -> None:
        self._tool_dir = tool_dir
        self._manifest = load_manifest(tool_dir / "manifest.yaml")
        self._registry = self._load_registry()

    @property
    def name(self) -> str:
        return self._manifest.name

    @property
    def manifest(self) -> ToolManifest:
        return self._manifest

    @property
    def tool_dir(self) -> Path:
        return self._tool_dir

    def is_enabled(self) -> bool:
        return self._manifest.enabled

    def _load_registry(self) -> dict[str, Any]:
        path = self._tool_dir / "registry.yaml"
        if not path.exists():
            return {}
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else {}

    def registry_entry(self) -> dict[str, Any]:
        if self._registry.get("operations"):
            entry = dict(self._registry)
            if self._manifest.supports_mcp and self._manifest.mcp_server:
                entry.setdefault("mcp_server", self._manifest.mcp_server)
            entry.setdefault("adapter", self.name)
            return entry
        return {}

    def operations(self) -> list[str]:
        return sorted((self.registry_entry().get("operations") or {}).keys())

    def parse_rules(self, query: str, backend_hint: str | None) -> IntentDocument | None:
        if backend_hint and backend_hint != self.name:
            return None
        return None

    def resolve(self, intent: IntentDocument, query: str) -> tuple[IntentDocument, str | None]:
        _ = query
        return intent, None

    def infer_keywords(self) -> list[str]:
        return list(self._manifest.infer_keywords)

    def validate_intent(self, intent: IntentDocument) -> None:
        if intent.backend != self.name:
            raise SafetyError(f"Intent backend '{intent.backend}' does not match tool '{self.name}'")
        if intent.operation not in self.operations():
            raise SafetyError(f"Unknown operation '{intent.operation}' for backend '{self.name}'")

    def validate_safety(self, intent: IntentDocument, *, request_read_only: bool) -> None:
        if not request_read_only and not intent.read_only:
            raise SafetyError("Write operations are blocked")

    def adapter_available(self) -> bool:
        return False

    async def execute(self, intent: IntentDocument, *, read_only: bool, max_rows: int) -> Any:
        raise NotImplementedError(f"Adapter not implemented for {self.name}")
