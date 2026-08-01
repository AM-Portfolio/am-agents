from __future__ import annotations

import logging
import os
from typing import Any

from temporalio.client import Client

logger = logging.getLogger(__name__)


class TemporalAdapter:
    def __init__(self) -> None:
        self._target = os.getenv("TEMPORAL_TARGET") or os.getenv("TEMPORAL_HOST") or "localhost:7233"
        self._namespace = os.getenv("TEMPORAL_NAMESPACE") or "default"

    @property
    def available(self) -> bool:
        return True

    async def _get_client(self) -> Client:
        return await Client.connect(self._target, namespace=self._namespace)

    async def execute(
        self, operation: str, params: dict[str, Any], *, read_only: bool, max_rows: int
    ) -> Any:
        client = await self._get_client()

        if operation == "list_workflows":
            status_filter = params.get("status")
            query = params.get("query")
            if status_filter and not query:
                query = f'ExecutionStatus = "{status_filter}"'

            results = []
            if query:
                async for wf in client.list_workflows(query):
                    results.append({
                        "workflow_id": wf.id,
                        "run_id": wf.run_id,
                        "type": wf.type,
                        "status": wf.status.name if wf.status else "UNKNOWN",
                        "start_time": str(wf.start_time),
                        "execution_time": str(wf.execution_time),
                    })
                    if len(results) >= max_rows:
                        break
            else:
                async for wf in client.list_workflows():
                    results.append({
                        "workflow_id": wf.id,
                        "run_id": wf.run_id,
                        "type": wf.type,
                        "status": wf.status.name if wf.status else "UNKNOWN",
                        "start_time": str(wf.start_time),
                        "execution_time": str(wf.execution_time),
                    })
                    if len(results) >= max_rows:
                        break

            return {
                "target": self._target,
                "namespace": self._namespace,
                "count": len(results),
                "workflows": results,
            }

        if operation == "describe_workflow":
            workflow_id = str(params["workflow_id"])
            run_id = params.get("run_id")
            handle = client.get_workflow_handle(workflow_id, run_id=run_id)
            desc = await handle.describe()

            return {
                "workflow_id": desc.id,
                "run_id": desc.run_id,
                "type": desc.type,
                "status": desc.status.name,
                "start_time": str(desc.start_time),
                "close_time": str(desc.close_time) if desc.close_time else None,
                "execution_time": str(desc.execution_time),
                "history_length": desc.history_length,
            }

        if operation == "query_workflow":
            workflow_id = str(params["workflow_id"])
            query_name = str(params["query_name"])
            run_id = params.get("run_id")
            handle = client.get_workflow_handle(workflow_id, run_id=run_id)
            res = await handle.query(query_name)
            return {
                "workflow_id": workflow_id,
                "query_name": query_name,
                "result": res,
            }

        if operation == "signal_workflow":
            workflow_id = str(params["workflow_id"])
            signal_name = str(params["signal_name"])
            arg = params.get("arg")
            run_id = params.get("run_id")
            handle = client.get_workflow_handle(workflow_id, run_id=run_id)
            if arg is not None:
                await handle.signal(signal_name, arg)
            else:
                await handle.signal(signal_name)
            return {
                "action": "signaled",
                "workflow_id": workflow_id,
                "signal_name": signal_name,
            }

        if operation == "terminate_workflow":
            workflow_id = str(params["workflow_id"])
            reason = str(params.get("reason", "Terminated via tool-agent MCP"))
            run_id = params.get("run_id")
            handle = client.get_workflow_handle(workflow_id, run_id=run_id)
            await handle.terminate(reason=reason)
            return {
                "action": "terminated",
                "workflow_id": workflow_id,
                "reason": reason,
            }

        raise ValueError(f"Unsupported temporal operation: {operation}")
