"""OpenProject TicketStore adapter."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import quote

from am_platform_ports.schemas.core import TicketRef

from am_platform_adapters.providers.openproject.client import OpenProjectClient


def _wp_id(ticket_ref: str) -> int:
    ref = ticket_ref.strip()
    if ref.startswith("op:wp:"):
        return int(ref.split(":", 2)[2])
    if ref.isdigit():
        return int(ref)
    raise ValueError(f"invalid OpenProject ticket_ref: {ticket_ref!r}")


def _assignee_href(assignee_ref: str) -> str:
    ref = assignee_ref.strip()
    if ref.startswith("op:user:"):
        return f"/api/v3/users/{ref.split(':', 2)[2]}"
    if ref.startswith("op:login:"):
        return f"/api/v3/users/{ref.split(':', 2)[2]}"  # resolved later if non-digit
    if ref.startswith("/api/v3/users/"):
        return ref
    if ref.isdigit():
        return f"/api/v3/users/{ref}"
    # bare login
    return f"/api/v3/users/{ref}"


# Lab status names → OpenProject status ids (kind-am-preprod defaults)
_STATUS_MAP = {
    "open": 1,
    "new": 1,
    "in_progress": 7,
    "in-progress": 7,
    "progress": 7,
    "closed": 12,
    "resolved": 12,
    "done": 12,
    "rejected": 14,
    "on_hold": 13,
    "hold": 13,
}


class OpenProjectTicketStore:
    """Work packages as tickets. ``ticket_ref`` = ``op:wp:{{id}}``."""

    def __init__(
        self,
        client: OpenProjectClient | None = None,
        *,
        project_id: int | None = None,
        type_id: int | None = None,
    ) -> None:
        self._client = client or OpenProjectClient()
        self._project_id = project_id or int(os.environ.get("OPENPROJECT_PROJECT_ID", "3"))
        self._type_id = type_id or int(os.environ.get("OPENPROJECT_TYPE_ID", "1"))  # Task

    def _public_url(self, wp_id: int) -> str:
        base = os.environ.get("OPENPROJECT_PUBLIC_URL") or os.environ.get(
            "OPENPROJECT_URL", "https://openproject.asrax.in"
        )
        # Prefer browser URL host even if API uses in-cluster endpoint
        if "svc.cluster.local" in base or "127.0.0.1" in base or "localhost" in base:
            base = os.environ.get("OPENPROJECT_PUBLIC_URL", "https://openproject.asrax.in")
        return f"{base.rstrip('/')}/work_packages/{wp_id}"

    def create(
        self,
        *,
        title: str,
        description: str,
        priority: str,
        labels: dict[str, str] | None = None,
    ) -> TicketRef:
        labels = labels or {}
        desc_parts = [description]
        if labels:
            desc_parts.append("\n\nLabels:\n" + "\n".join(f"- {k}: {v}" for k, v in labels.items()))
        if priority:
            desc_parts.append(f"\n\nAlert priority: {priority}")
        body: dict[str, Any] = {
            "subject": (title or "Alert")[:255],
            "description": {"format": "plain", "raw": "".join(desc_parts)[:100_000]},
            "_links": {
                "project": {"href": f"/api/v3/projects/{self._project_id}"},
                "type": {"href": f"/api/v3/types/{self._type_id}"},
            },
        }
        data = self._client.post("/api/v3/work_packages", body)
        wp_id = int(data["id"])
        return TicketRef(ticket_ref=f"op:wp:{wp_id}", url=self._public_url(wp_id))

    def _get_lock(self, wp_id: int) -> int:
        data = self._client.get(f"/api/v3/work_packages/{wp_id}")
        return int(data["lockVersion"])

    def assign(self, *, ticket_ref: str, assignee_ref: str) -> None:
        """Assign work package to an existing OpenProject user (project member)."""
        wp_id = _wp_id(ticket_ref)
        href = _assignee_href(assignee_ref)
        # If login-style ref slipped through, resolve via users API
        if href.startswith("/api/v3/users/") and not href.split("/")[-1].isdigit():
            login = href.split("/")[-1]
            filt = quote(
                json.dumps([{"login": {"operator": "=", "values": [login]}}]),
                safe="",
            )
            data = self._client.get(f"/api/v3/users?filters={filt}&pageSize=1")
            els = data.get("_embedded", {}).get("elements") or []
            if not els:
                raise ValueError(f"OpenProject user login not found: {login!r}")
            href = f"/api/v3/users/{els[0]['id']}"
        lock = self._get_lock(wp_id)
        self._client.patch(
            f"/api/v3/work_packages/{wp_id}",
            {"_links": {"assignee": {"href": href}}},
            lock_version=lock,
        )

    def comment(self, *, ticket_ref: str, body: str) -> None:
        wp_id = _wp_id(ticket_ref)
        self._client.post(
            f"/api/v3/work_packages/{wp_id}/activities",
            {"comment": {"format": "plain", "raw": body}},
        )

    def update_status(self, *, ticket_ref: str, status: str) -> None:
        wp_id = _wp_id(ticket_ref)
        key = status.strip().lower().replace(" ", "_")
        status_id = _STATUS_MAP.get(key)
        if status_id is None and key.isdigit():
            status_id = int(key)
        if status_id is None:
            raise ValueError(f"unknown status {status!r}; known: {sorted(_STATUS_MAP)}")
        lock = self._get_lock(wp_id)
        self._client.patch(
            f"/api/v3/work_packages/{wp_id}",
            {"_links": {"status": {"href": f"/api/v3/statuses/{status_id}"}}},
            lock_version=lock,
        )
