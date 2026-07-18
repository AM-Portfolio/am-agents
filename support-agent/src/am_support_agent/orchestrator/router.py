"""Capability router — prefer tool-agent; gate legacy db-agent."""

from __future__ import annotations

from am_support_agent.contracts.schemas import AgentCard
from am_support_agent.registry import AgentRegistry


class Router:
    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    def route(
        self,
        *,
        agent_id: str | None = None,
        capability: str = "",
        require_legacy_db: bool = False,
    ) -> AgentCard:
        legacy = (
            require_legacy_db
            or "legacy.db-agent" in capability
            or capability.startswith("db.")
        )
        if agent_id == "db-agent" and not legacy:
            raise PermissionError(
                "db-agent requires explicit legacy.db-agent request"
            )
        return self.registry.resolve_agent(
            agent_id=agent_id,
            require_legacy_db=legacy,
            capability_prefix=capability or None,
        )
