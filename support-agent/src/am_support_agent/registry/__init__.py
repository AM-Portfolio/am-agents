"""Agent registry loader."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from am_support_agent.contracts.enums import A2AOp
from am_support_agent.contracts.schemas import (
    AgentAuthSpec,
    AgentCard,
    AgentHealthSpec,
    AgentLimits,
    CapabilitySpec,
    TaskBudget,
)


def default_registry_path() -> Path:
    env = os.getenv("AGENT_PLATFORM_REGISTRY", "").strip()
    if env:
        return Path(env)
    packaged = Path(__file__).resolve().parent / "agents.yaml"
    if packaged.is_file():
        return packaged
    repo = Path(__file__).resolve().parents[3] / "registry" / "agents.yaml"
    return repo


def load_registry_dict(path: Path | None = None) -> dict[str, Any]:
    registry_path = path or default_registry_path()
    with registry_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError("agents.yaml must be a mapping")
    return data


def _resolve_base_url(entry: dict[str, Any]) -> str:
    env_name = entry.get("base_url_env")
    if env_name:
        from_env = os.getenv(str(env_name), "").strip()
        if from_env:
            return from_env.rstrip("/")
    return str(entry.get("default_base_url", "")).rstrip("/")


def _parse_ops(raw: list[Any]) -> list[A2AOp]:
    return [A2AOp(str(op)) for op in raw]


def agent_card_from_entry(entry: dict[str, Any]) -> AgentCard:
    auth_raw = entry.get("auth") or {}
    limits_raw = entry.get("limits") or {}
    caps: list[CapabilitySpec] = []
    for cap in entry.get("capabilities") or []:
        caps.append(
            CapabilitySpec(
                id=str(cap["id"]),
                ops=_parse_ops(list(cap.get("ops") or [])),
                preferred=bool(entry.get("preferred", False)),
            )
        )
    return AgentCard(
        agent_id=str(entry["agent_id"]),
        display_name=str(entry.get("display_name") or entry["agent_id"]),
        base_url=_resolve_base_url(entry),
        capabilities=caps,
        health=AgentHealthSpec(
            path=str(entry.get("health_path") or "/health"),
            ready_path=entry.get("ready_path"),
        ),
        auth=AgentAuthSpec(
            scheme=str(auth_raw.get("scheme") or "none"),
            header=auth_raw.get("header"),
        ),
        limits=AgentLimits(
            multi_replica_status=bool(limits_raw.get("multi_replica_status", False)),
        ),
        tags=[str(t) for t in (entry.get("tags") or [])],
        preferred=bool(entry.get("preferred", False)),
    )


class AgentRegistry:
    """Allowlisted agents + routing preference."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data
        platform = data.get("platform") or {}
        self.platform_agent_id = str(platform.get("agent_id") or "support-agent")
        self.platform_display_name = str(
            platform.get("display_name") or "Support Agent"
        )
        self._cards = {
            card.agent_id: card
            for card in (agent_card_from_entry(e) for e in data.get("agents") or [])
        }
        defaults = data.get("defaults") or {}
        budgets = defaults.get("budgets") or {}
        self.prefer = str(defaults.get("prefer") or "tool-agent")
        self.default_budget = TaskBudget(
            max_fanout=int(budgets.get("max_fanout", 8)),
            max_latency_ms=int(budgets.get("max_latency_ms", 120_000)),
            max_cost_units=float(budgets.get("max_cost_units", 100)),
        )

    def get(self, agent_id: str) -> AgentCard:
        try:
            return self._cards[agent_id]
        except KeyError as exc:
            raise KeyError(f"agent not in registry allowlist: {agent_id}") from exc

    def list_cards(self) -> list[AgentCard]:
        return list(self._cards.values())

    def contains(self, agent_id: str) -> bool:
        return agent_id in self._cards

    def resolve_agent(
        self,
        *,
        agent_id: str | None = None,
        require_legacy_db: bool = False,
        capability_prefix: str | None = None,
    ) -> AgentCard:
        if agent_id == "db-agent" and not require_legacy_db:
            raise PermissionError(
                "db-agent requires explicit legacy.db-agent request "
                "(set require_legacy_db=True)"
            )
        if agent_id:
            return self.get(agent_id)
        if capability_prefix and capability_prefix.startswith("ui."):
            return self.get("ui-test-agent")
        if require_legacy_db:
            return self.get("db-agent")
        return self.get(self.prefer)


@lru_cache(maxsize=8)
def get_registry(path: str | None = None) -> AgentRegistry:
    p = Path(path) if path else default_registry_path()
    return AgentRegistry(load_registry_dict(p))
