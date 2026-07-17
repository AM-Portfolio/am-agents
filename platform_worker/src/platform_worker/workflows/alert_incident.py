"""AlertIncidentWorkflow — Gate A: verify before done (or Approve override)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from platform_worker.activities import alert_incident as acts
    from platform_worker.activities import infra as iacts
    from platform_worker.activities import verify as vacts


@dataclass
class AlertIncidentInput:
    tracking_id: str
    alert: dict[str, Any]
    run_ref: str | None = None


@workflow.defn(name="AlertIncidentWorkflow")
class AlertIncidentWorkflow:
    def __init__(self) -> None:
        self._resolved = False
        self._refired = False
        self._closed = False
        self._approved = False
        self._run_ref: str | None = None
        self._ticket_ref: str | None = None
        self._verify_run_ref: str | None = None
        self._verify_status: str | None = None

    @workflow.signal(name="alert.resolved")
    async def alert_resolved(self) -> None:
        self._resolved = True

    @workflow.signal(name="alert.refired")
    async def alert_refired(self) -> None:
        self._refired = True

    @workflow.signal(name="approve")
    async def approve(self) -> None:
        """Human override for Gate A when verify failed."""
        self._approved = True

    @workflow.query
    def status(self) -> dict[str, Any]:
        return {
            "run_ref": self._run_ref,
            "ticket_ref": self._ticket_ref,
            "verify_run_ref": self._verify_run_ref,
            "verify_status": self._verify_status,
            "resolved": self._resolved,
            "refired": self._refired,
            "approved": self._approved,
            "closed": self._closed,
        }

    @workflow.run
    async def run(self, input: AlertIncidentInput | dict[str, Any]) -> dict[str, Any]:
        if isinstance(input, dict):
            tracking_id = str(input.get("tracking_id") or "")
            alert = dict(input.get("alert") or {})
            pre_run_ref = input.get("run_ref")
        else:
            tracking_id = input.tracking_id
            alert = input.alert
            pre_run_ref = input.run_ref

        retry = RetryPolicy(maximum_attempts=3)
        short = timedelta(seconds=60)
        verify_timeout = timedelta(minutes=5)

        run = await workflow.execute_activity(
            acts.create_incident_run,
            {
                "tracking_id": tracking_id,
                "workflow_id": workflow.info().workflow_id,
                "incident_ref": tracking_id,
                "run_ref": pre_run_ref,
            },
            start_to_close_timeout=short,
            retry_policy=retry,
        )
        self._run_ref = run["run_ref"]

        triage = await workflow.execute_activity(
            acts.triage_alert,
            {"run_ref": self._run_ref, "alert": alert},
            start_to_close_timeout=short,
            retry_policy=retry,
        )

        ticket = await workflow.execute_activity(
            acts.create_and_assign_ticket,
            {"run_ref": self._run_ref, "triage": triage, "alert": alert},
            start_to_close_timeout=short,
            retry_policy=retry,
        )
        self._ticket_ref = ticket["ticket_ref"]

        await workflow.execute_activity(
            acts.notify_ticket_created,
            {
                "run_ref": self._run_ref,
                "ticket_ref": ticket["ticket_ref"],
                "channel_ref": ticket["channel_ref"],
                "incident_ref": tracking_id,
                "title": f"[{triage['priority']}] {triage.get('summary', 'Alert')}",
                "body": f"Ticket {ticket['ticket_ref']} assigned to {ticket['assignee_ref']}",
            },
            start_to_close_timeout=short,
            retry_policy=retry,
        )

        # Wait for resolve / silence ignored (no signal) / first closer wins
        await workflow.wait_condition(lambda: self._resolved or self._closed)

        # InfraOps allowlisted fix → work_done (ADR-005 before verify)
        await workflow.execute_activity(
            iacts.plan_and_execute_fix,
            {
                "run_ref": self._run_ref,
                "incident_ref": tracking_id,
                "ticket_ref": self._ticket_ref,
                "alert": alert,
            },
            start_to_close_timeout=short,
            retry_policy=retry,
        )

        # --- Gate A: verify before done ---
        spawned = await workflow.execute_activity(
            vacts.spawn_verify_run,
            {
                "parent_run_ref": self._run_ref,
                "incident_ref": tracking_id,
                "ticket_ref": self._ticket_ref,
                "workflow_id": workflow.info().workflow_id,
            },
            start_to_close_timeout=short,
            retry_policy=retry,
        )
        self._verify_run_ref = spawned["verify_run_ref"]

        verify_result = await workflow.execute_activity(
            vacts.claim_and_execute_verify,
            {
                "verify_run_ref": self._verify_run_ref,
                "incident_ref": tracking_id,
                "worker_id": f"wf-{workflow.info().workflow_id}",
            },
            start_to_close_timeout=verify_timeout,
            retry_policy=retry,
        )
        self._verify_status = verify_result["status"]

        final_status = "passed"
        closer = "verify.passed"
        if verify_result["status"] == "passed":
            final_status = "passed"
            closer = "verify.passed"
        else:
            # needs human Approve to close
            await workflow.execute_activity(
                acts.mark_run_status,
                {
                    "run_ref": self._run_ref,
                    "status": "needs_human",
                    "summary": {
                        "ticket_ref": self._ticket_ref,
                        "verify_run_ref": self._verify_run_ref,
                        "verify_status": verify_result["status"],
                        "gate": "awaiting_approve",
                    },
                },
                start_to_close_timeout=short,
                retry_policy=retry,
            )
            await workflow.wait_condition(lambda: self._approved or self._closed)
            final_status = "passed"
            closer = "approve.override"

        await workflow.execute_activity(
            acts.mark_run_status,
            {
                "run_ref": self._run_ref,
                "status": final_status,
                "summary": {
                    "ticket_ref": self._ticket_ref,
                    "verify_run_ref": self._verify_run_ref,
                    "verify_status": self._verify_status,
                    "closer": closer,
                },
            },
            start_to_close_timeout=short,
            retry_policy=retry,
        )
        self._closed = True
        return {
            "run_ref": self._run_ref,
            "ticket_ref": self._ticket_ref,
            "verify_run_ref": self._verify_run_ref,
            "verify_status": self._verify_status,
            "status": final_status,
            "closer": closer,
        }
