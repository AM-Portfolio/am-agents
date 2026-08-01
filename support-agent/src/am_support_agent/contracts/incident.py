"""Incident acceptance-gate and memory contracts (support-agent owned)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from am_support_agent.contracts.capabilities import (
    DirectoryOwner,
    ObserveEvidence,
    WorkItemRef,
)
from am_support_agent.contracts.enums import IncidentValidationStatus
from am_support_agent.contracts.schemas import EvidenceItem


class PolicyQuerySpec(BaseModel):
    kind: Literal["metrics", "logs"] = "metrics"
    query_ref: str = ""
    lookback_seconds: int = 300
    freshness_seconds: int = 180


class IncidentEvidencePolicy(BaseModel):
    """Versioned deterministic evidence / recovery policy for an alert class."""

    policy_id: str
    policy_version: str = "1"
    match_alertnames: list[str] = Field(default_factory=list)
    match_fingerprints: list[str] = Field(default_factory=list)
    environments: list[str] = Field(default_factory=list)
    require_metrics: bool = True
    require_logs: bool = False
    metric_queries: list[PolicyQuerySpec] = Field(default_factory=list)
    log_queries: list[PolicyQuerySpec] = Field(default_factory=list)
    min_samples: int = 1
    recovery_stability_samples: int = 2
    recovery_stability_seconds: int = 60
    healthy_when_firing: bool = False
    max_verify_rounds: int = 10
    observation_interval_minutes: int = 2


class EvidencePredicateResult(BaseModel):
    name: str
    passed: bool
    detail: str = ""


class EvidenceObservation(BaseModel):
    """Parsed observation — transport_ok is never sufficient for recovery."""

    kind: str
    transport_ok: bool = False
    parseable: bool = False
    healthy: bool | None = None
    observed_at: str = ""
    summary: str = ""
    query_ref: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    predicates: list[EvidencePredicateResult] = Field(default_factory=list)


class RemediationStep(BaseModel):
    capability: str
    args_schema: dict[str, Any] = Field(default_factory=dict)
    effect: Literal["remediation", "admin", "notify", "observe"] = "admin"
    risk: str = "update"
    version: str = "1"


class RemediationCandidate(BaseModel):
    """Reusable fix extracted only from verified closures with remediation effect."""

    candidate_id: str = ""
    episode_id: str = ""
    tracking_id: str = ""
    service: str = ""
    env: str = ""
    fingerprint: str = ""
    policy_id: str = ""
    policy_version: str = ""
    steps: list[RemediationStep] = Field(default_factory=list)
    step_hash: str = ""
    preconditions: dict[str, Any] = Field(default_factory=dict)
    status: str = "proposed"
    created_at: str = ""


class AlertFeedbackRequest(BaseModel):
    kind: Literal["silence", "disable_candidate", "note"] = "note"
    tracking_id: str = ""
    workflow_id: str = ""
    requester: str = ""
    reason: str = ""
    duration_minutes: int = 60
    env: str = ""
    service: str = ""
    matchers: dict[str, str] = Field(default_factory=dict)
    request_id: str = ""
    notes: str = ""


class ApprovalPayload(BaseModel):
    purpose: Literal["investigation", "known_fix", "silence"]
    request_id: str = ""
    actor: str = ""
    timestamp: str = ""
    scope_hash: str = ""
    notes: str = ""


class IncidentContext(BaseModel):
    """Normalized context after ticket read-back + evidence gather."""

    tracking_id: str
    run_ref: str = ""
    alert: dict[str, Any] = Field(default_factory=dict)
    work_item: WorkItemRef | None = None
    owner: DirectoryOwner | None = None
    observe: list[ObserveEvidence] = Field(default_factory=list)
    evidence_observations: list[EvidenceObservation] = Field(default_factory=list)
    policy_id: str = ""
    policy_version: str = ""
    similar_incidents: list[str] = Field(default_factory=list)
    similar_summaries: list[dict[str, Any]] = Field(default_factory=list)
    memory_refs: list[str] = Field(default_factory=list)
    catalog_refs: list[str] = Field(default_factory=list)
    known_fix: RemediationCandidate | None = None
    built_at: str = ""


class IncidentValidation(BaseModel):
    """Fail-closed gate before investigation notification / remediation."""

    status: IncidentValidationStatus
    confidence: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    freshness_at: str = ""
    work_item_ok: bool = False
    policy_version: str = ""
    prompt_key: str = ""
    prompt_version: str | None = None
    prompt_source: str = ""


class IncidentEpisode(BaseModel):
    """Append-only episodic memory record (redacted before persistence)."""

    episode_id: str
    tracking_id: str
    run_ref: str = ""
    context: IncidentContext | None = None
    validation: IncidentValidation | None = None
    decision: str = ""
    actions: list[dict[str, Any]] = Field(default_factory=list)
    outcome: str = ""
    verify_status: str = ""
    evidence: list[EvidenceItem] = Field(default_factory=list)
    human_feedback_refs: list[str] = Field(default_factory=list)
    provenance: dict[str, str] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class MemoryQuery(BaseModel):
    """Postgres episode retrieval (semantic/Qdrant is post-canary)."""

    service: str = ""
    env: str = ""
    fingerprint: str = ""
    labels: dict[str, str] = Field(default_factory=dict)
    limit: int = 10

    def has_discriminating_filter(self) -> bool:
        return bool(self.service or self.env or self.fingerprint or self.labels)


class IncidentFeedbackEvent(BaseModel):
    """Learning/feedback capture for an incident episode (not A2A FeedbackEvent)."""

    feedback_id: str = ""
    episode_id: str = ""
    tracking_id: str = ""
    run_ref: str = ""
    kind: str = "outcome"
    rating: str = ""
    labels: list[str] = Field(default_factory=list)
    notes: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    auto_promote: bool = False
    idempotency_key: str | None = None
    created_at: str = ""


def episode_id_for(*, tracking_id: str, run_ref: str) -> str:
    """Deterministic episode id for Temporal activity retries."""
    tid = (tracking_id or "").strip() or "unknown"
    rid = (run_ref or "").strip() or tid
    return f"ep-{tid}-{rid}"
