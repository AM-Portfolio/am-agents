from __future__ import annotations

from typing import Any

from tools._shared.grafana_time import grafana_time_to_rfc3339
from tools._shared.mcp_remote_client import RemoteMcpClient

READ_ONLY_OPERATIONS = frozenset(
    {
        "query_logs",
        "list_labels",
        "list_label_values",
        "query_patterns",
        "find_error_logs",
        "query_metrics",
        "search_dashboards",
        "get_dashboard",
        "list_datasources",
    }
)


class McpSatelliteAdapter:
    def __init__(
        self,
        *,
        url: str,
        operation_map: dict[str, str],
        timeout_seconds: float = 30.0,
    ) -> None:
        self._client = RemoteMcpClient(url, timeout_seconds=timeout_seconds)
        self._operation_map = dict(operation_map)

    @property
    def available(self) -> bool:
        return bool(self._client.url)

    def mcp_tool_name(self, operation: str) -> str:
        if operation not in self._operation_map:
            raise ValueError(f"Unsupported operation: {operation}")
        return self._operation_map[operation]

    def _map_time_param(self, params: dict[str, Any], source: str, target: str) -> None:
        if source in params:
            params[target] = grafana_time_to_rfc3339(str(params.pop(source)))

    def _normalize_params(self, operation: str, params: dict[str, Any], *, max_rows: int) -> dict[str, Any]:
        out = dict(params)
        if operation == "query_logs":
            if "logql" not in out and "query" in out:
                out["logql"] = out.pop("query")
            if "limit" not in out and max_rows:
                out["limit"] = max_rows
            self._map_time_param(out, "start", "startRfc3339")
            if "startRfc3339" in out:
                out["startRfc3339"] = grafana_time_to_rfc3339(str(out["startRfc3339"]))
            self._map_time_param(out, "end", "endRfc3339")
            if "endRfc3339" in out:
                out["endRfc3339"] = grafana_time_to_rfc3339(str(out["endRfc3339"]))
        if operation == "find_error_logs":
            self._map_time_param(out, "start", "startRfc3339")
            if "startRfc3339" in out:
                out["startRfc3339"] = grafana_time_to_rfc3339(str(out["startRfc3339"]))
            self._map_time_param(out, "end", "endRfc3339")
            if "endRfc3339" in out:
                out["endRfc3339"] = grafana_time_to_rfc3339(str(out["endRfc3339"]))
        if operation == "query_metrics":
            if "expr" in out and "query" not in out:
                out["query"] = out.pop("expr")
            if "limit" not in out and max_rows:
                out["limit"] = max_rows
        return out

    async def execute(
        self,
        operation: str,
        params: dict[str, Any],
        *,
        read_only: bool,
        max_rows: int,
    ) -> Any:
        if operation not in READ_ONLY_OPERATIONS:
            raise ValueError(f"Operation not allowed: {operation}")
        if not read_only:
            raise ValueError("Grafana satellite adapter is read-only")
        mcp_tool = self.mcp_tool_name(operation)
        arguments = self._normalize_params(operation, params, max_rows=max_rows)
        data = await self._client.call_tool(mcp_tool, arguments)
        return {"operation": operation, "mcp_tool": mcp_tool, "data": data}
