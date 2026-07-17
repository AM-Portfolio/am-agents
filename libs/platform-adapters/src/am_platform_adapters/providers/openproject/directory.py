"""OpenProject-backed Directory — resolve to an existing project member."""

from __future__ import annotations

import json
import os
from urllib.parse import quote

from am_platform_ports.schemas.core import DirectoryHit

from am_platform_adapters.providers.openproject.client import OpenProjectClient


def _href_user_id(href: str | None) -> str | None:
    if not href:
        return None
    # /api/v3/users/5
    parts = href.rstrip("/").split("/")
    return parts[-1] if parts else None


class OpenProjectDirectory:
    """
    Resolve alert labels → an **existing** OpenProject user who is a member
    of ``OPENPROJECT_PROJECT_ID``.

    Priority:
      1. labels ``assignee`` / ``owner`` matching member login or name
      2. ``OPENPROJECT_ASSIGNEE_MAP`` (label value → login or user id)
      3. ``OPENPROJECT_DEFAULT_ASSIGNEE_LOGIN`` (default ``munish``)
      4. ``OPENPROJECT_DEFAULT_ASSIGNEE_ID`` if set
      5. first project member
    """

    def __init__(
        self,
        client: OpenProjectClient | None = None,
        *,
        project_id: int | None = None,
        default_assignee_id: int | None = None,
        default_assignee_login: str | None = None,
        assignee_map: dict[str, str] | None = None,
        channel_ref: str | None = None,
    ) -> None:
        self._client = client or OpenProjectClient()
        self._project_id = project_id or int(os.environ.get("OPENPROJECT_PROJECT_ID", "3"))
        env_id = os.environ.get("OPENPROJECT_DEFAULT_ASSIGNEE_ID", "").strip()
        self._default_id = (
            default_assignee_id
            if default_assignee_id is not None
            else (int(env_id) if env_id else None)
        )
        self._default_login = (
            default_assignee_login
            or os.environ.get("OPENPROJECT_DEFAULT_ASSIGNEE_LOGIN", "munish")
        ).strip().lower()
        raw = os.environ.get("OPENPROJECT_ASSIGNEE_MAP", "").strip()
        if assignee_map is not None:
            self._map = {k.lower(): str(v) for k, v in assignee_map.items()}
        elif raw:
            parsed = json.loads(raw)
            self._map = {str(k).lower(): str(v) for k, v in parsed.items()}
        else:
            # Lab defaults: team/service label → existing project member logins
            self._map = {
                "lab": "munish",
                "fintech": "munish",
                "platform": "sagar",
                "infra": "gyan",
            }
        self._channel = channel_ref or os.environ.get("OPENPROJECT_NOTIFY_CHANNEL", "cliq:lab")
        self._members: list[dict[str, str]] | None = None

    def _load_members(self) -> list[dict[str, str]]:
        if self._members is not None:
            return self._members
        filt = quote(
            json.dumps([{"project": {"operator": "=", "values": [str(self._project_id)]}}]),
            safe="",
        )
        data = self._client.get(f"/api/v3/memberships?filters={filt}&pageSize=100")
        members: list[dict[str, str]] = []
        for el in data.get("_embedded", {}).get("elements", []):
            links = el.get("_links") or {}
            principal = links.get("principal") or {}
            href = principal.get("href") or ""
            if "/users/" not in href:
                continue  # skip groups
            uid = _href_user_id(href)
            if not uid:
                continue
            title = (principal.get("title") or "").strip()
            login = ""
            try:
                user = self._client.get(f"/api/v3/users/{uid}")
                login = str(user.get("login") or "").strip().lower()
            except Exception:
                login = title.lower().split()[0] if title else uid
            members.append({"id": uid, "login": login, "name": title.lower()})
        self._members = members
        return members

    def _find_member(self, hint: str) -> dict[str, str] | None:
        hint = hint.strip().lower()
        if not hint:
            return None
        members = self._load_members()
        if hint.isdigit():
            for m in members:
                if m["id"] == hint:
                    return m
            return None
        for m in members:
            if m["login"] == hint or hint in m["name"] or m["name"] == hint:
                return m
        return None

    def resolve(self, *, labels: dict[str, str], priority: str) -> DirectoryHit:
        from am_platform_ports.agent_identity import cliq_channel_for_env, normalize_alert_env

        _ = priority
        labels = {str(k): str(v) for k, v in (labels or {}).items()}
        env = normalize_alert_env(labels=labels)
        team = labels.get("team") or labels.get("service") or "lab"
        members = self._load_members()
        if not members:
            raise RuntimeError(
                f"OpenProject project {self._project_id} has no user members to assign"
            )

        chosen: dict[str, str] | None = None

        # 1) explicit assignee/owner label → existing member
        for key in ("assignee", "owner"):
            val = (labels.get(key) or "").strip()
            if val:
                chosen = self._find_member(val)
                if chosen:
                    break

        # 2) team/service via map → login/id that must exist on project
        if chosen is None:
            for key in ("team", "service", "env"):
                val = (labels.get(key) or "").strip().lower()
                if val and val in self._map:
                    chosen = self._find_member(self._map[val])
                    if chosen:
                        break

        # 3) default login / id
        if chosen is None and self._default_login:
            chosen = self._find_member(self._default_login)
        if chosen is None and self._default_id is not None:
            chosen = self._find_member(str(self._default_id))

        # 4) first project member
        if chosen is None:
            chosen = members[0]

        return DirectoryHit(
            assignee_ref=f"op:user:{chosen['id']}",
            team=team,
            channel_ref=cliq_channel_for_env(env),
        )
