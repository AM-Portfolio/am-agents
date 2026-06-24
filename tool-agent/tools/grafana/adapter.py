from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.models.intent import IntentDocument
from tools._shared.mcp_satellite_adapter import McpSatelliteAdapter

logger = logging.getLogger(__name__)

_OPERATION_MAP = {
    "query_logs": "query_loki_logs",
    "list_labels": "list_loki_label_names",
    "list_label_values": "list_loki_label_values",
    "query_patterns": "query_loki_patterns",
    "find_error_logs": "find_error_pattern_logs",
    "query_metrics": "query_prometheus",
    "search_dashboards": "search_dashboards",
    "get_dashboard": "get_dashboard_by_uid",
    "list_datasources": "list_datasources",
}


class GrafanaAdapter:
    def __init__(self) -> None:
        self._satellite: McpSatelliteAdapter | None = None

    def _satellite_adapter(self) -> McpSatelliteAdapter:
        if self._satellite is None:
            url = settings.GRAFANA_MCP_URL or ""
            self._satellite = McpSatelliteAdapter(
                url=url,
                operation_map=_OPERATION_MAP,
                timeout_seconds=settings.GRAFANA_MCP_TIMEOUT_SECONDS,
            )
        return self._satellite

    @property
    def available(self) -> bool:
        return bool(settings.GRAFANA_MCP_URL)

    async def execute(
        self,
        operation: str,
        params: dict[str, Any],
        *,
        read_only: bool,
        max_rows: int,
    ) -> Any:
        if not settings.GRAFANA_MCP_URL:
            raise RuntimeError("GRAFANA_MCP_URL not configured")
        return await self._satellite_adapter().execute(
            operation,
            params,
            read_only=read_only,
            max_rows=max_rows,
        )
