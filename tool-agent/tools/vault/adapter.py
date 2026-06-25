from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from tools._shared.mcp_remote_client import RemoteMcpClient
from tools.vault.safety import READ_OPERATIONS, WRITE_OPERATIONS

logger = logging.getLogger(__name__)

_OPERATION_MAP = {
    "list_secrets": "list_secrets",
    "read_secret": "read_secret",
    "write_secret": "write_secret",
    "delete_secret": "delete_secret",
    "list_mounts": "list_mounts",
}


class VaultMcpAdapter:
    def __init__(self) -> None:
        self._client: RemoteMcpClient | None = None

    def _client_instance(self) -> RemoteMcpClient:
        if self._client is None:
            url = settings.VAULT_MCP_URL or ""
            self._client = RemoteMcpClient(url, timeout_seconds=settings.VAULT_MCP_TIMEOUT_SECONDS)
        return self._client

    @property
    def available(self) -> bool:
        return bool(settings.VAULT_MCP_URL)

    def _default_mount(self) -> str:
        return settings.VAULT_MCP_MOUNT or "apps"

    def _normalize_path(self, path: str) -> str:
        if path.startswith("apps/data/"):
            return path[len("apps/") :]
        if path.startswith("apps/") and not path.startswith("apps/data/"):
            rest = path[len("apps/") :]
            return rest if rest.startswith("data/") else f"data/{rest}"
        return path

    def _normalize_params(self, operation: str, params: dict[str, Any]) -> dict[str, Any]:
        out = dict(params)
        out["mount"] = out.get("mount") or self._default_mount()
        if operation == "list_mounts":
            return {}
        if "path" in out and out["path"]:
            out["path"] = self._normalize_path(str(out["path"]))
        return out

    async def execute(
        self,
        operation: str,
        params: dict[str, Any],
        *,
        read_only: bool,
        max_rows: int,
    ) -> Any:
        if operation not in _OPERATION_MAP:
            raise ValueError(f"Unsupported vault operation: {operation}")
        if operation in WRITE_OPERATIONS:
            if read_only or not settings.VAULT_MCP_WRITES_ENABLED:
                raise RuntimeError("Vault writes are disabled")
        elif operation not in READ_OPERATIONS:
            raise ValueError(f"Operation not allowed: {operation}")

        mcp_tool = _OPERATION_MAP[operation]
        arguments = self._normalize_params(operation, params)
        _ = max_rows
        data = await self._client_instance().call_tool(mcp_tool, arguments)
        return {"operation": operation, "mcp_tool": mcp_tool, "data": data}
