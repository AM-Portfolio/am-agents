from __future__ import annotations

from typing import Any


class Adapter:
    """Delegates to the existing grafana plugin adapter when available."""

    def __init__(self) -> None:
        self._grafana = None
        try:
            from tools.grafana.adapter import GrafanaAdapter

            self._grafana = GrafanaAdapter()
        except Exception:
            self._grafana = None

    @property
    def available(self) -> bool:
        return bool(self._grafana and getattr(self._grafana, "available", False))

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        assert self._grafana is not None
        mapping = {
            "metrics.query": "query_metrics",
            "logs.query": "query_logs",
            "timeseries.query": "query_metrics",
        }
        grafana_op = mapping.get(operation)
        if not grafana_op:
            raise ValueError(operation)
        data = await self._grafana.execute(grafana_op, params, read_only=read_only, max_rows=100)
        return {
            "kind": operation.split(".", 1)[0],
            "query_ref": params.get("query_ref") or params.get("query") or "",
            "status": "ok",
            "summary": f"grafana:{grafana_op}",
            "data": data if isinstance(data, dict) else {"value": data},
        }
