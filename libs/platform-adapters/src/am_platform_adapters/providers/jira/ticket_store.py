"""Jira TicketStore adapter — same TicketStore port as OpenProject."""

from __future__ import annotations

import os
from typing import Any

from am_platform_ports.schemas.core import TicketRef

from am_platform_adapters.providers.jira.client import JiraClient


def _issue_key(ticket_ref: str) -> str:
    ref = ticket_ref.strip()
    if ref.startswith("jira:"):
        return ref.split(":", 1)[1]
    if "-" in ref:
        return ref
    raise ValueError(f"invalid Jira ticket_ref: {ticket_ref!r}")


def _account_id(assignee_ref: str) -> str:
    ref = assignee_ref.strip()
    if ref.startswith("jira:user:"):
        return ref.split(":", 2)[2]
    return ref


# Lab-friendly status name → common transition names (matched case-insensitively)
_STATUS_TRANSITION = {
    "open": ("to do", "open", "backlog"),
    "new": ("to do", "open", "backlog"),
    "in_progress": ("in progress", "start progress"),
    "in-progress": ("in progress", "start progress"),
    "closed": ("done", "close", "resolved"),
    "resolved": ("done", "resolve", "closed"),
    "done": ("done", "close"),
}


class JiraTicketStore:
    """Issues as tickets. ``ticket_ref`` = ``jira:{{KEY}}``."""

    def __init__(
        self,
        client: JiraClient | None = None,
        *,
        project_key: str | None = None,
        issue_type: str | None = None,
    ) -> None:
        self._client = client or JiraClient()
        self._project = (project_key or os.environ.get("JIRA_PROJECT_KEY", "OPS")).strip()
        self._issue_type = (issue_type or os.environ.get("JIRA_ISSUE_TYPE", "Task")).strip()

    def create(
        self,
        *,
        title: str,
        description: str,
        priority: str,
        labels: dict[str, str] | None = None,
    ) -> TicketRef:
        labels = labels or {}
        desc = description
        if labels:
            desc += "\n\nLabels:\n" + "\n".join(f"- {k}: {v}" for k, v in labels.items())
        if priority:
            desc += f"\n\nAlert priority: {priority}"
        body: dict[str, Any] = {
            "fields": {
                "project": {"key": self._project},
                "summary": (title or "Alert")[:255],
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": desc[:30000]}],
                        }
                    ],
                },
                "issuetype": {"name": self._issue_type},
                "labels": [f"{k}-{v}"[:255] for k, v in list(labels.items())[:10]],
            }
        }
        data = self._client.post("/rest/api/3/issue", body)
        key = str(data["key"])
        base = os.environ.get("JIRA_BASE_URL", "").rstrip("/")
        return TicketRef(ticket_ref=f"jira:{key}", url=f"{base}/browse/{key}" if base else None)

    def assign(self, *, ticket_ref: str, assignee_ref: str) -> None:
        key = _issue_key(ticket_ref)
        self._client.put(
            f"/rest/api/3/issue/{key}/assignee",
            {"accountId": _account_id(assignee_ref)},
        )

    def comment(self, *, ticket_ref: str, body: str) -> None:
        key = _issue_key(ticket_ref)
        self._client.post(
            f"/rest/api/3/issue/{key}/comment",
            {
                "body": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": body[:30000]}],
                        }
                    ],
                }
            },
        )

    def update_status(self, *, ticket_ref: str, status: str) -> None:
        key = _issue_key(ticket_ref)
        wanted = _STATUS_TRANSITION.get(status.strip().lower().replace(" ", "_"), (status.lower(),))
        transitions = self._client.get(f"/rest/api/3/issue/{key}/transitions")
        for t in transitions.get("transitions") or []:
            name = str(t.get("name") or "").lower()
            if any(w in name for w in wanted):
                self._client.post(
                    f"/rest/api/3/issue/{key}/transitions",
                    {"transition": {"id": t["id"]}},
                )
                return
        raise ValueError(f"no Jira transition matching status={status!r} for {key}")
