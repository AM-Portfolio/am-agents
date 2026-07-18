"""Incident acceptance-gate and memory contracts (support-agent owned)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from am_support_agent.contracts.capabilities import (
    DirectoryOwner,
    ObserveEvidence,
    WorkItemRef,
)
from am_support_agent.contracts.enums import IncidentValidationStatus
from am_support_agent.contracts.schemas import EvidenceItem


class IncidentContext(BaseModel):
    """Normalized context after ticket read-back + evidence gather."""

    tracking_id: str
    run_ref: str = ""
    alert: dict[str, Any] = Field(default_factory=dict)
    work_item: WorkItemRef | None = None
    owner: DirectoryOwner | None = None
    observe: list[ObserveEvidence] = Field(default_factory=list)
    similar_incidents: list[str] = Field(default_factory=list)
    memory_refs: list[str] = Field(default_factory=list)
    catalog_refs: list[str] = Field(default_factory=list)
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


class MemoryQuery(BaseModel):
    """Postgres episode retrieval (semantic/Qdrant is post-canary)."""

    service: str = ""
    env: str = ""
    fingerprint: str = ""
    labels: dict[str, str] = Field(default_factory=dict)
    limit: int = 10


class IncidentFeedbackEvent(BaseModel):
    """Learning/feedback capture for an incident episode (not A2A FeedbackEvent)."""

    episode_id: str = ""
    tracking_id: str = ""
    run_ref: str = ""
    kind: str = "outcome"
    labels: list[str] = Field(default_factory=list)
    notes: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    auto_promote: bool = False
