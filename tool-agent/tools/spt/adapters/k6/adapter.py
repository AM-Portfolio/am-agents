from __future__ import annotations

import os
from typing import Any


class Adapter:
    """Sandbox-gated k6 engine stub — real process execution lands with SPT parity."""

    @property
    def available(self) -> bool:
        return os.environ.get("SPT_K6_ENABLED", "false").lower() in {"1", "true", "yes"}

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        _ = read_only
        if not params.get("sandbox", True) and os.environ.get("SPT_ALLOW_UNSANDBOXED", "false").lower() not in {
            "1",
            "true",
            "yes",
        }:
            raise RuntimeError("k6 SPT requires sandbox=true")
        if operation == "test-data.prepare":
            return {"prep_ref": f"k6:prep:{params.get('demand_ref') or 'default'}", "ready": True}
        if operation == "execute":
            return {
                "async_operation_ref": f"k6:run:{params.get('demand_ref') or 'default'}",
                "status": "accepted",
                "engine": "k6",
            }
        if operation == "status":
            return {"async_operation_ref": params.get("async_operation_ref") or "", "status": "succeeded", "engine": "k6"}
        if operation == "cancel":
            return {"async_operation_ref": params.get("async_operation_ref") or "", "status": "cancelled", "engine": "k6"}
        raise ValueError(operation)
