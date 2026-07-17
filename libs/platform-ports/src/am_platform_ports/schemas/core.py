"""Core alert / ticket / notify schemas."""

from typing import Any

from pydantic import BaseModel, Field


class TriageResult(BaseModel):
    priority: str
    category: str
    summary: str
    labels: dict[str, str] = Field(default_factory=dict)


class TicketRef(BaseModel):
    ticket_ref: str
    url: str | None = None


class NotifyCard(BaseModel):
    event: str
    title: str
    body: str
    refs: dict[str, str] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)


class DirectoryHit(BaseModel):
    assignee_ref: str
    team: str | None = None
    channel_ref: str | None = None


class DocRef(BaseModel):
    """Opaque document pointer — provider is baked into docs_ref."""

    docs_ref: str
    provider: str
    url: str | None = None
    key: str | None = None


class InfraOpsAction(BaseModel):
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)


class InfraOpsPlan(BaseModel):
    plan_ref: str
    actions: list[InfraOpsAction] = Field(default_factory=list)


class WorkDoneResult(BaseModel):
    work_ref: str
    plan_ref: str
    summary: str
    actions_ran: list[str] = Field(default_factory=list)
