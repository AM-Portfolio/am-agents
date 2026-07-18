from __future__ import annotations

import itertools
import threading
from typing import Any


class MemoryAdapter:
    _counter = itertools.count(1)
    _lock = threading.Lock()
    _runs: dict[str, dict[str, Any]] = {}

    @property
    def available(self) -> bool:
        return True

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        _ = read_only
        with self._lock:
            if operation == "test-data.prepare":
                prep_ref = f"mem:prep:{next(self._counter)}"
                return {"prep_ref": prep_ref, "demand_ref": params.get("demand_ref") or "", "ready": True}
            if operation == "execute":
                run_ref = f"mem:spt:{next(self._counter)}"
                self._runs[run_ref] = {"status": "running", "demand_ref": params.get("demand_ref") or ""}
                return {"async_operation_ref": run_ref, "status": "running"}
            ref = str(params.get("async_operation_ref") or params.get("run_ref") or "")
            if operation == "status":
                run = self._runs.get(ref) or {"status": "unknown"}
                return {"async_operation_ref": ref, **run}
            if operation == "cancel":
                if ref in self._runs:
                    self._runs[ref]["status"] = "cancelled"
                return {"async_operation_ref": ref, "status": "cancelled"}
            raise ValueError(operation)
