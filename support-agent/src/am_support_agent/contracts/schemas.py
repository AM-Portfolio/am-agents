"""A2A envelope schemas (platform-facing)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from am_support_agent.contracts.enums import (
    A2AOp,
    FeedbackRating,
    SupportDomain,
    TaskStatus,
)


class TaskBudget(BaseModel):
    max_latency_ms: int = 120_000
    max_cost_units: float = 100.0
    max_fanout: int = 8


class TaskAuth(BaseModel):
    service_token_ref: str | None = None


class TaskRequest(BaseModel):
    task_id: str
    correlation_id: str = ""
    agent_id: str
    capability: str = ""
    op: A2AOp
    business_domain: SupportDomain = SupportDomain.UNKNOWN
    requires_human: bool = False
    idempotency_key: str | None = None
    budget: TaskBudget = Field(default_factory=TaskBudget)
    auth: TaskAuth = Field(default_factory=TaskAuth)
    payload: dict[str, Any] = Field(default_factory=dict)


class EvidenceItem(BaseModel):
    kind: str
    ref: str
    provenance: str = ""


class TaskError(BaseModel):
    code: str
    message: str
    retryable: bool = False


class TaskMetrics(BaseModel):
    latency_ms: int = 0
    cost_units: float = 0.0


class TaskResult(BaseModel):
    task_id: str
    status: TaskStatus
    agent_id: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    error: TaskError | None = None
    metrics: TaskMetrics = Field(default_factory=TaskMetrics)
    data: dict[str, Any] = Field(default_factory=dict)


class CapabilitySpec(BaseModel):
    id: str
    ops: list[A2AOp]
    preferred: bool = False


class AgentHealthSpec(BaseModel):
    path: str = "/health"
    ready_path: str | None = None


class AgentAuthSpec(BaseModel):
    scheme: str = "none"
    header: str | None = None


class AgentLimits(BaseModel):
    multi_replica_status: bool = False


class AgentCard(BaseModel):
    agent_id: str
    display_name: str
    base_url: str
    capabilities: list[CapabilitySpec] = Field(default_factory=list)
    health: AgentHealthSpec = Field(default_factory=AgentHealthSpec)
    auth: AgentAuthSpec = Field(default_factory=AgentAuthSpec)
    limits: AgentLimits = Field(default_factory=AgentLimits)
    tags: list[str] = Field(default_factory=list)
    preferred: bool = False


class FeedbackEvent(BaseModel):
    task_id: str
    run_ref: str = ""
    rating: FeedbackRating
    labels: list[str] = Field(default_factory=list)
    notes: str = ""
    proposed_change: dict[str, Any] | None = None
