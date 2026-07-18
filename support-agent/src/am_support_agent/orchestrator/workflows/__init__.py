"""Workflows package — lazy exports so Temporal sandbox can load one workflow
module without importing activity/adapter graphs from sibling workflows.
"""

from __future__ import annotations

from typing import Any

__all__ = ["SupportA2AWorkflow", "AlertIncidentWorkflow", "SptRunWorkflow"]


def __getattr__(name: str) -> Any:
    if name == "SupportA2AWorkflow":
        from am_support_agent.orchestrator.workflows.a2a_run import SupportA2AWorkflow

        return SupportA2AWorkflow
    if name == "AlertIncidentWorkflow":
        from am_support_agent.orchestrator.workflows.alert_incident import (
            AlertIncidentWorkflow,
        )

        return AlertIncidentWorkflow
    if name == "SptRunWorkflow":
        from am_support_agent.orchestrator.workflows.spt_run import SptRunWorkflow

        return SptRunWorkflow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
