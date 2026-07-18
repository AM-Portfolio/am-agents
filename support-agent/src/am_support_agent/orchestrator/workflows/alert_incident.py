"""AlertIncident workflow — acceptance gate + HITL for inconclusive."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from am_support_agent.orchestrator.activities.incident import (
        bootstrap_incident,
        finalize_incident,
        record_hitl,
    )
    from am_support_agent.orchestrator.hitl import (
        SIGNAL_ALERT_REFIRED,
        SIGNAL_ALERT_RESOLVED,
        SIGNAL_APPROVE,
        HitlState,
    )


_ACTIVITY_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=5,
)


@workflow.defn(name="AlertIncidentWorkflow")
class AlertIncidentWorkflow:
    """Parallel replacement — parity gated via SUPPORT_AGENT_INCIDENT_PARITY."""

    def __init__(self) -> None:
        self._hitl = HitlState()
        self._tracking_id: str = ""
        self._phase: str = "init"
        self._bootstrap: dict[str, Any] = {}

    @workflow.signal(name=SIGNAL_ALERT_RESOLVED)
    async def alert_resolved(self) -> None:
        self._hitl.apply_signal(SIGNAL_ALERT_RESOLVED)

    @workflow.signal(name=SIGNAL_ALERT_REFIRED)
    async def alert_refired(self) -> None:
        self._hitl.apply_signal(SIGNAL_ALERT_REFIRED)

    @workflow.signal(name=SIGNAL_APPROVE)
    async def approve(self) -> None:
        self._hitl.apply_signal(SIGNAL_APPROVE)

    @workflow.query
    def status(self) -> dict[str, Any]:
        return {
            "tracking_id": self._tracking_id,
            "phase": self._phase,
            "module": "support-agent",
            "bootstrap": self._bootstrap,
            **self._hitl.as_dict(),
        }

    @workflow.run
    async def run(self, input: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(input or {})
        self._tracking_id = str(
            payload.get("tracking_id") or workflow.info().workflow_id
        )
        self._phase = "bootstrap"
        self._bootstrap = await workflow.execute_activity(
            bootstrap_incident,
            {
                "tracking_id": self._tracking_id,
                "run_ref": str(payload.get("run_ref") or self._tracking_id),
                "alert": dict(payload.get("alert") or {}),
            },
            start_to_close_timeout=timedelta(seconds=120),
            retry_policy=_ACTIVITY_RETRY,
        )
        if self._bootstrap.get("gated"):
            self._phase = "gated"
            return {
                "status": "gated",
                "tracking_id": self._tracking_id,
                "bootstrap": self._bootstrap,
                "hitl": self._hitl.as_dict(),
            }

        if self._bootstrap.get("stop"):
            self._phase = "not_confirmed"
            return {
                "status": "not_confirmed",
                "tracking_id": self._tracking_id,
                "bootstrap": self._bootstrap,
            }

        actions = list(self._bootstrap.get("actions") or [])
        if self._bootstrap.get("needs_hitl"):
            self._phase = "awaiting_hitl"
            await workflow.wait_condition(lambda: self._hitl.waiting_satisfied())
            self._phase = "hitl_recorded"
            recorded = await workflow.execute_activity(
                record_hitl,
                {
                    "tracking_id": self._tracking_id,
                    "episode_id": self._bootstrap.get("episode_id"),
                    "hitl": self._hitl.as_dict(),
                },
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=_ACTIVITY_RETRY,
            )
            if not self._hitl.approved and not self._hitl.resolved:
                self._hitl.closed = True
                self._phase = "closed"
                return {
                    "status": "inconclusive_closed",
                    "tracking_id": self._tracking_id,
                    "bootstrap": self._bootstrap,
                    "hitl": recorded,
                }
            # On approve, continue to finalize with planned actions (or empty)
            if self._hitl.approved and not actions:
                actions = [
                    {
                        "capability": "chat.message.send",
                        "args": {
                            "channel_ref": "cliq:lab",
                            "body": f"HITL approved investigation for {self._tracking_id}",
                        },
                    }
                ]

        if self._bootstrap.get("continue") or self._hitl.approved:
            self._phase = "finalize"
            finalized = await workflow.execute_activity(
                finalize_incident,
                {
                    "tracking_id": self._tracking_id,
                    "actions": actions,
                    "episode_id": self._bootstrap.get("episode_id"),
                },
                start_to_close_timeout=timedelta(seconds=120),
                retry_policy=_ACTIVITY_RETRY,
            )
            self._hitl.closed = True
            self._phase = "closed"
            return {
                "status": "confirmed",
                "tracking_id": self._tracking_id,
                "bootstrap": self._bootstrap,
                "finalize": finalized,
                "hitl": self._hitl.as_dict(),
            }

        self._hitl.closed = True
        self._phase = "closed"
        return {
            "status": "closed",
            "tracking_id": self._tracking_id,
            "bootstrap": self._bootstrap,
            "hitl": self._hitl.as_dict(),
        }
