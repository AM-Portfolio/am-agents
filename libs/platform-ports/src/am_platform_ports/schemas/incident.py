"""Incident analysis decision DTOs (LLM routing)."""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


IncidentDecisionKind = Literal["needs_human", "auto_infra", "ignore"]


class ProposedAction(BaseModel):
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)


class IncidentDecision(BaseModel):
    decision: IncidentDecisionKind
    confidence: float = 0.0
    rationale: str = ""
    handoff_agent: str | None = None  # e.g. kagent_infra
    proposed_actions: list[ProposedAction] = Field(default_factory=list)
    ticket_update: str = ""
    resolution_note: str = ""

    @field_validator("rationale", "ticket_update", "resolution_note", mode="before")
    @classmethod
    def _none_to_empty(cls, v: Any) -> Any:
        # Real LLMs often emit null for unused optional strings.
        return "" if v is None else v

    @field_validator("proposed_actions", mode="before")
    @classmethod
    def _none_actions_to_list(cls, v: Any) -> Any:
        return [] if v is None else v
