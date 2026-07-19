from __future__ import annotations

import os
from typing import Any

from tools.work_item.adapters.openproject.client import OpenProjectClient


class Adapter:
    def __init__(self) -> None:
        self._client: OpenProjectClient | None = None
        try:
            self._client = OpenProjectClient()
        except Exception:
            self._client = None
        self._project_id = int(os.environ.get("OPENPROJECT_PROJECT_ID", "3"))

    @property
    def available(self) -> bool:
        return self._client is not None

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        _ = read_only
        if operation != "owner.resolve":
            raise ValueError(operation)
        assert self._client is not None
        # Best-effort: first project membership as owner; callers should refine with catalog.
        data = self._client.get(f"/api/v3/projects/{self._project_id}/available_assignees?pageSize=1")
        els = (data.get("_embedded") or {}).get("elements") or []
        if not els:
            raise RuntimeError("no OpenProject assignees available")
        user = els[0]
        return {
            "assignee_ref": f"op:user:{user.get('id')}",
            "assignee_name": user.get("name") or "",
            "assignee_email": user.get("email") or "",
            "channel_ref": params.get("channel_ref") or "cliq:lab",
            "owner_source": "openproject",
        }
