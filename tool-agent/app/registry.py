from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.models.intent import IntentDocument, ToolCall, UNIVERSAL_BACKENDS
from tools._loader import get_tool, merged_registry

logger = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self) -> None:
        self._registry = merged_registry()
        self._backends = settings.load_backends_config()

    def reload(self) -> None:
        self._registry = merged_registry()
        self._backends = settings.load_backends_config()

    @property
    def backends(self) -> dict[str, Any]:
        return self._registry.get("backends") or {}

    def _backend_cfg(self, backend: str) -> dict[str, Any]:
        return self.backends.get(backend) or {}

    def _resolve_mcp_server(self, backend: str) -> str | None:
        tool = get_tool(backend)
        if tool and tool.manifest.supports_mcp:
            if backend in UNIVERSAL_BACKENDS and settings.MCP_UNIVERSAL_GATEWAY == "toolbox":
                if settings.MCP_ENABLED or settings.TOOLBOX_URL:
                    return "toolbox"
            server = tool.manifest.mcp_server
            if server and settings.MCP_ENABLED:
                return str(server)
        cfg = self._backend_cfg(backend)
        server = cfg.get("mcp_server")
        if server and settings.MCP_ENABLED:
            return str(server)
        return None

    def resolve(self, intent: IntentDocument) -> ToolCall:
        cfg = self._backend_cfg(intent.backend)
        operations = cfg.get("operations") or {}
        op_cfg = operations.get(intent.operation)
        if not op_cfg:
            raise ValueError(f"No registry entry for {intent.backend}.{intent.operation}")

        mcp_server = self._resolve_mcp_server(intent.backend)
        use_mcp = bool(mcp_server and settings.MCP_ENABLED)

        if use_mcp:
            return ToolCall(
                backend=intent.backend,
                operation=intent.operation,
                params=intent.params,
                source="mcp",
                mcp_server=mcp_server,
                mcp_tool=op_cfg.get("mcp_tool"),
                adapter_method=str(op_cfg.get("adapter_method") or intent.operation),
                read_only=intent.read_only,
            )

        adapter_method = op_cfg.get("adapter_method") or intent.operation
        return ToolCall(
            backend=intent.backend,
            operation=intent.operation,
            params=intent.params,
            source="adapter",
            adapter_method=str(adapter_method),
            read_only=intent.read_only,
        )

    def servers_config(self) -> dict[str, Any]:
        from pathlib import Path
        import yaml

        from app.config import AGENT_ROOT

        path = AGENT_ROOT / "config" / "servers.yaml"
        if not path.exists():
            return {}
        with path.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}


_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def reset_registry() -> None:
    global _registry
    _registry = None
