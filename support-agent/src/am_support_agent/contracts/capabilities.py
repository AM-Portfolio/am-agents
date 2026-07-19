"""Neutral capability DTOs — generic IDs; vendors live only in tool-agent adapters."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from am_support_agent.contracts.enums import ApprovalRisk


class ApprovalMetadata(BaseModel):
    risk: ApprovalRisk = ApprovalRisk.READ
    requires_human: bool = False
    reason: str = ""


class IdempotencyMetadata(BaseModel):
    key: str
    plan_hash: str | None = None
    operation_key: str | None = None


class CapabilityCall(BaseModel):
    """Generic tool-agent invocation envelope (no vendor names)."""

    capability: str
    args: dict[str, Any] = Field(default_factory=dict)
    approval: ApprovalMetadata = Field(default_factory=ApprovalMetadata)
    idempotency: IdempotencyMetadata | None = None
    provider_hint: str | None = None


class WorkItemRef(BaseModel):
    work_item_ref: str
    url: str = ""
    provider: str = ""
    status: str = ""
    assignee_ref: str = ""
    labels: dict[str, str] = Field(default_factory=dict)
    updated_at: str = ""
    lock_version: str = ""
    correlation_id: str = ""


class WorkItemCreateRequest(BaseModel):
    title: str
    description: str = ""
    priority: str = "P3"
    labels: dict[str, str] = Field(default_factory=dict)
    assignee_ref: str | None = None


class DirectoryOwner(BaseModel):
    assignee_ref: str
    assignee_name: str = ""
    assignee_email: str = ""
    backup_name: str = ""
    backup_email: str = ""
    channel_ref: str = "cliq:lab"
    owner_source: str = ""


class ChatSendRequest(BaseModel):
    channel_ref: str
    body: str = ""
    card: dict[str, Any] | None = None


class MailSendRequest(BaseModel):
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    subject: str
    html_body: str = ""
    text_body: str = ""


class DocumentRef(BaseModel):
    bucket: str = ""
    object_key: str
    checksum: str = ""
    content_type: str = ""
    size_bytes: int | None = None


class ObserveEvidence(BaseModel):
    kind: str
    query_ref: str = ""
    window_start: str = ""
    window_end: str = ""
    freshness_at: str = ""
    status: str = "ok"
    summary: str = ""
    ref: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class SptExecuteRequest(BaseModel):
    demand_ref: str
    target_ref: str = ""
    policy_ref: str = ""
    sandbox: bool = True
    args: dict[str, Any] = Field(default_factory=dict)
