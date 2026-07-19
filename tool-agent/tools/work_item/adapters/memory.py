from __future__ import annotations

import itertools
import threading
from typing import Any


class MemoryAdapter:
    _counter = itertools.count(1)
    _lock = threading.Lock()
    _items: dict[str, dict[str, Any]] = {}

    @property
    def available(self) -> bool:
        return True

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        _ = read_only
        with self._lock:
            if operation == "create":
                wid = f"mem:wi:{next(self._counter)}"
                item = {
                    "work_item_ref": wid,
                    "title": params.get("title") or "untitled",
                    "description": params.get("description") or "",
                    "status": "open",
                    "assignee_ref": params.get("assignee_ref") or "",
                    "labels": params.get("labels") or {},
                    "comments": [],
                }
                self._items[wid] = item
                return dict(item)
            ref = str(params.get("work_item_ref") or params.get("id") or "")
            if operation == "search":
                q = str(params.get("query") or "").lower()
                hits = [dict(v) for v in self._items.values() if not q or q in str(v).lower()]
                return {"items": hits}
            if not ref or ref not in self._items:
                if operation == "get":
                    raise KeyError(f"work item not found: {ref}")
                raise KeyError(f"work item not found: {ref}")
            item = self._items[ref]
            if operation == "get":
                return dict(item)
            if operation == "comment":
                item["comments"].append(params.get("body") or "")
                return {"work_item_ref": ref, "comments": list(item["comments"])}
            if operation == "assign":
                item["assignee_ref"] = params.get("assignee_ref") or ""
                return {"work_item_ref": ref, "assignee_ref": item["assignee_ref"]}
            if operation == "transition":
                item["status"] = params.get("status") or item["status"]
                return {"work_item_ref": ref, "status": item["status"]}
            raise ValueError(f"unknown operation {operation}")
