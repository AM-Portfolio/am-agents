"""Runtime helpers: auth, budgets, idempotency, routing."""

from __future__ import annotations

import hashlib
import os
import uuid
from typing import Any

from am_support_agent.contracts.schemas import TaskBudget, TaskRequest
from am_support_agent.registry import AgentRegistry


def new_task_id() -> str:
    return uuid.uuid4().hex


def enforce_execute_idempotency(request: TaskRequest) -> None:
    if request.op.value == "execute" and not request.idempotency_key:
        raise ValueError("idempotency_key required for execute")


def merge_budget(request: TaskRequest, defaults: TaskBudget) -> TaskBudget:
    return TaskBudget(
        max_latency_ms=min(request.budget.max_latency_ms, defaults.max_latency_ms),
        max_cost_units=min(request.budget.max_cost_units, defaults.max_cost_units),
        max_fanout=min(request.budget.max_fanout, defaults.max_fanout),
    )


def validate_fanout(n: int, budget: TaskBudget) -> None:
    if n > budget.max_fanout:
        raise ValueError(f"fanout {n} exceeds max_fanout {budget.max_fanout}")


class IdempotencyStore:
    """In-memory execute cache for gateway v2 until RunStore is wired."""

    def __init__(self) -> None:
        self._seen: dict[str, Any] = {}

    def key(self, agent_id: str, idempotency_key: str) -> str:
        raw = f"{agent_id}:{idempotency_key}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, agent_id: str, idempotency_key: str) -> Any | None:
        return self._seen.get(self.key(agent_id, idempotency_key))

    def put(self, agent_id: str, idempotency_key: str, value: Any) -> None:
        self._seen[self.key(agent_id, idempotency_key)] = value


def require_gateway_token(token: str | None) -> None:
    """Auth for support-agent gateway — distinct from legacy GATEWAY_API_TOKEN."""
    expected = (
        os.getenv("SUPPORT_AGENT_API_TOKEN", "").strip()
        or os.getenv("AGENT_PLATFORM_API_TOKEN", "").strip()
    )
    if not expected:
        raise PermissionError(
            "SUPPORT_AGENT_API_TOKEN (or AGENT_PLATFORM_API_TOKEN) not configured"
        )
    if not token or token != expected:
        raise PermissionError("invalid token")


def route_request(
    registry: AgentRegistry,
    *,
    agent_id: str | None,
    capability: str = "",
    require_legacy_db: bool = False,
) -> str:
    card = registry.resolve_agent(
        agent_id=agent_id,
        require_legacy_db=require_legacy_db
        or "legacy.db-agent" in capability
        or capability.startswith("db."),
        capability_prefix=capability or None,
    )
    return card.agent_id
