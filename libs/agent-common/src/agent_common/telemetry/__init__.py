"""Shared agent-work telemetry contract for AM agents."""

from agent_common.telemetry.events import AgentWorkEvent, build_event, dedupe_key
from agent_common.telemetry.sanitize import sanitize_attributes
from agent_common.telemetry.vocabulary import (
    ALLOWED_LABEL_KEYS,
    EVENT_NAMES,
    OUTCOME_MAP,
    WorkOutcome,
    WorkStatus,
    map_domain_status,
)

__all__ = [
    "ALLOWED_LABEL_KEYS",
    "EVENT_NAMES",
    "OUTCOME_MAP",
    "AgentWorkEvent",
    "WorkOutcome",
    "WorkStatus",
    "build_event",
    "dedupe_key",
    "map_domain_status",
    "sanitize_attributes",
]
