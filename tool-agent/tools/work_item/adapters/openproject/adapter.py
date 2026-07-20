from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import quote

from tools.work_item.adapters.openproject.client import OpenProjectClient


def _wp_id(ticket_ref: str) -> int:
    ref = ticket_ref.strip()
    if ref.startswith("op:wp:"):
        return int(ref.split(":", 2)[2])
    if ref.isdigit():
        return int(ref)
    raise ValueError(f"invalid OpenProject work_item_ref: {ticket_ref!r}")


class Adapter:
    def __init__(self) -> None:
        self._client: OpenProjectClient | None = None
        try:
            self._client = OpenProjectClient()
        except Exception:
            self._client = None
        self._project_id = int(os.environ.get("OPENPROJECT_PROJECT_ID", "3"))
        self._type_id = int(os.environ.get("OPENPROJECT_TYPE_ID", "1"))

    @property
    def available(self) -> bool:
        return self._client is not None

    def _public_url(self, wp_id: int) -> str:
        base = os.environ.get("OPENPROJECT_PUBLIC_URL") or os.environ.get("OPENPROJECT_URL", "")
        return f"{base.rstrip('/')}/work_packages/{wp_id}"

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        _ = read_only
        assert self._client is not None
        if operation == "create":
            body = {
                "subject": str(params.get("title") or "Alert")[:255],
                "description": {"format": "plain", "raw": str(params.get("description") or "")[:100_000]},
                "_links": {
                    "project": {"href": f"/api/v3/projects/{self._project_id}"},
                    "type": {"href": f"/api/v3/types/{self._type_id}"},
                },
            }
            data = self._client.post("/api/v3/work_packages", body)
            wp_id = int(data["id"])
            return {
                "work_item_ref": f"op:wp:{wp_id}",
                "url": self._public_url(wp_id),
                "status": "open",
                "lock_version": str(data.get("lockVersion") or ""),
            }
        if operation == "get":
            wp_id = _wp_id(str(params.get("work_item_ref") or params.get("id") or ""))
            data = self._client.get(f"/api/v3/work_packages/{wp_id}")
            assignee = ((data.get("_links") or {}).get("assignee") or {}).get("href") or ""
            return {
                "work_item_ref": f"op:wp:{wp_id}",
                "title": data.get("subject") or "",
                "status": ((data.get("_links") or {}).get("status") or {}).get("title") or "",
                "assignee_ref": assignee,
                "url": self._public_url(wp_id),
                "lock_version": str(data.get("lockVersion") or ""),
                "updated_at": data.get("updatedAt") or "",
            }
        if operation == "search":
            q = str(params.get("query") or "")
            filters = []
            if q:
                filters.append({"subject": {"operator": "~", "values": [q]}})
            filt = quote(json.dumps(filters), safe="")
            data = self._client.get(f"/api/v3/work_packages?filters={filt}&pageSize=20")
            els = (data.get("_embedded") or {}).get("elements") or []
            return {
                "items": [
                    {"work_item_ref": f"op:wp:{el['id']}", "title": el.get("subject") or ""}
                    for el in els
                ]
            }
        if operation == "comment":
            wp_id = _wp_id(str(params.get("work_item_ref") or ""))
            self._client.post(
                f"/api/v3/work_packages/{wp_id}/activities",
                {"comment": {"format": "plain", "raw": str(params.get("body") or "")}},
            )
            return {"work_item_ref": f"op:wp:{wp_id}", "ok": True}
        if operation == "assign":
            wp_id = _wp_id(str(params.get("work_item_ref") or ""))
            data = self._client.get(f"/api/v3/work_packages/{wp_id}")
            lock = int(data["lockVersion"])
            href = str(params.get("assignee_ref") or "")
            if href.isdigit():
                href = f"/api/v3/users/{href}"
            elif href.startswith("op:user:"):
                href = f"/api/v3/users/{href.split(':', 2)[2]}"
            self._client.patch(
                f"/api/v3/work_packages/{wp_id}",
                {"lockVersion": lock, "_links": {"assignee": {"href": href}}},
            )
            return {"work_item_ref": f"op:wp:{wp_id}", "assignee_ref": href}
        if operation == "transition":
            wp_id = _wp_id(str(params.get("work_item_ref") or ""))
            data = self._client.get(f"/api/v3/work_packages/{wp_id}")
            lock = int(data["lockVersion"])
            status_id = params.get("status_id") or params.get("status")
            self._client.patch(
                f"/api/v3/work_packages/{wp_id}",
                {
                    "lockVersion": lock,
                    "_links": {"status": {"href": f"/api/v3/statuses/{status_id}"}},
                },
            )
            return {"work_item_ref": f"op:wp:{wp_id}", "status": str(status_id)}
        raise ValueError(f"unknown operation {operation}")
