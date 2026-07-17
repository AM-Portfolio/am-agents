"""AlertIncidentWorkflow — LLM route: needs_human | auto_infra | ignore (+ legacy path)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from platform_worker.activities import alert_incident as acts
    from platform_worker.activities import analyze as aan
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
        self._verify_evidence: list[dict[str, Any]] = []
        self._verify_reason: str | None = None
        self._decision: str | None = None

    @workflow.signal(name="alert.resolved")
    async def alert_resolved(self) -> None:
        self._resolved = True

    @workflow.signal(name="alert.refired")
    async def alert_refired(self) -> None:
        self._refired = True

    @workflow.signal(name="approve")
    async def approve(self) -> None:
        self._approved = True

    @workflow.query
    def status(self) -> dict[str, Any]:
        return {
            "run_ref": self._run_ref,
            "ticket_ref": self._ticket_ref,
            "verify_run_ref": self._verify_run_ref,
            "verify_status": self._verify_status,
            "verify_evidence": list(self._verify_evidence),
            "verify_reason": self._verify_reason,
            "decision": self._decision,
            "resolved": self._resolved,
            "refired": self._refired,
            "approved": self._approved,
            "closed": self._closed,
        }

    async def _verify_and_close(
        self,
        *,
        tracking_id: str,
        retry: RetryPolicy,
        short: timedelta,
        verify_timeout: timedelta,
        closer_prefix: str,
        decision: dict[str, Any] | None = None,
        channel_ref: str = "cliq:lab",
        prior_attempts: list[Any] | None = None,
        env: str = "",
        alert: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
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
                "env": env,
                "alert": alert or {},
            },
            start_to_close_timeout=verify_timeout,
            retry_policy=retry,
        )
        self._verify_status = verify_result["status"]
        self._verify_evidence = list(
            verify_result.get("verify_evidence")
            or verify_result.get("evidence")
            or []
        )
        self._verify_reason = str(
            verify_result.get("verify_reason")
            or f"verify {verify_result['status']}"
        )

        final_status = "passed"
        closer = f"{closer_prefix}.verify.passed"
        if verify_result["status"] != "passed":
            attempts = list(prior_attempts or [])
            attempts.append(
                {
                    "step": "verify",
                    "status": "failed",
                    "verify_status": verify_result["status"],
                    "verify_run_ref": self._verify_run_ref,
                    "verify_reason": self._verify_reason,
                    "verify_evidence": self._verify_evidence,
                }
            )
            await workflow.execute_activity(
                aan.escalate_unsolved,
                {
                    "run_ref": self._run_ref,
                    "ticket_ref": self._ticket_ref,
                    "channel_ref": channel_ref,
                    "env": env,
                    "decision": decision or {"decision": "auto_infra", "rationale": closer_prefix},
                    "attempts": attempts,
                    "failure_reason": self._verify_reason
                    or f"verify gate failed: {verify_result['status']}",
                    "verify_status": verify_result["status"],
                    "extra": (
                        "Agent accepted auto path but recovery could not be verified. "
                        f"Details: {self._verify_reason}"
                    ),
                },
                start_to_close_timeout=short,
                retry_policy=retry,
            )
            await workflow.wait_condition(lambda: self._approved or self._resolved or self._closed)
            final_status = "passed"
            closer = f"{closer_prefix}.unsolved.human"
        else:
            await workflow.execute_activity(
                aan.close_incident_ticket,
                {
                    "run_ref": self._run_ref,
                    "ticket_ref": self._ticket_ref,
                    "channel_ref": channel_ref,
                    "env": env,
                    "closer": closer,
                    "decision": (decision or {}).get("decision") or closer_prefix,
                    "note": (
                        "Verify passed. Ticket closed by IT-Support-agent. "
                        "Grafana alert may still fire until resolved. "
                        f"Evidence: {self._verify_reason}"
                    ),
                },
                start_to_close_timeout=short,
                retry_policy=retry,
            )

        await workflow.execute_activity(
            acts.mark_run_status,
            {
                "run_ref": self._run_ref,
                "status": final_status,
                "summary": {
                    "ticket_ref": self._ticket_ref,
                    "verify_run_ref": self._verify_run_ref,
                    "verify_status": self._verify_status,
                    "verify_reason": self._verify_reason,
                    "verify_evidence": self._verify_evidence,
                    "decision": self._decision,
                    "closer": closer,
                    "env": env,
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
            "verify_evidence": self._verify_evidence,
            "verify_reason": self._verify_reason,
            "decision": self._decision,
            "status": final_status,
            "closer": closer,
            "env": env,
        }

    @workflow.run
    async def run(self, input: AlertIncidentInput | dict[str, Any]) -> dict[str, Any]:
        if isinstance(input, dict):
            tracking_id = str(input.get("tracking_id") or "")
            alert = dict(input.get("alert") or {})
            pre_run_ref = input.get("run_ref")
            use_llm = bool(input.get("alert_analysis_llm", True))
        else:
            tracking_id = input.tracking_id
            alert = input.alert
            pre_run_ref = input.run_ref
            use_llm = True

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
        env = str(ticket.get("env") or (alert.get("labels") or {}).get("env") or "")

        await workflow.execute_activity(
            acts.notify_ticket_created,
            {
                "run_ref": self._run_ref,
                "ticket_ref": ticket["ticket_ref"],
                "channel_ref": ticket["channel_ref"],
                "incident_ref": tracking_id,
                "env": env,
                "title": f"[{triage['priority']}] {triage.get('summary', 'Alert')}",
                "body": f"Ticket {ticket['ticket_ref']} assigned to {ticket['assignee_ref']} env={env}",
            },
            start_to_close_timeout=short,
            retry_policy=retry,
        )

        if use_llm:
            decision = await workflow.execute_activity(
                aan.analyze_incident,
                {"run_ref": self._run_ref, "alert": alert},
                start_to_close_timeout=short,
                retry_policy=retry,
            )
            self._decision = decision.get("decision")
            env = str(decision.get("env") or env)

            await workflow.execute_activity(
                aan.apply_ticket_decision,
                {
                    "run_ref": self._run_ref,
                    "ticket_ref": self._ticket_ref,
                    "channel_ref": ticket["channel_ref"],
                    "decision": decision,
                    "env": env,
                },
                start_to_close_timeout=short,
                retry_policy=retry,
            )

            if decision.get("decision") == "ignore":
                await workflow.execute_activity(
                    aan.close_incident_ticket,
                    {
                        "run_ref": self._run_ref,
                        "ticket_ref": self._ticket_ref,
                        "channel_ref": ticket["channel_ref"],
                        "env": env,
                        "closer": "ignore",
                        "decision": "ignore",
                        "note": "Ignored as noise. Ticket closed by IT-Support-agent.",
                    },
                    start_to_close_timeout=short,
                    retry_policy=retry,
                )
                self._closed = True
                return {
                    "run_ref": self._run_ref,
                    "ticket_ref": self._ticket_ref,
                    "decision": "ignore",
                    "status": "cancelled",
                    "closer": "ignore",
                    "env": env,
                }

            if decision.get("decision") == "needs_human":
                await workflow.wait_condition(lambda: self._approved or self._resolved or self._closed)
                await workflow.execute_activity(
                    acts.mark_run_status,
                    {
                        "run_ref": self._run_ref,
                        "status": "passed",
                        "summary": {
                            "ticket_ref": self._ticket_ref,
                            "decision": "needs_human",
                            "closer": "human.approve_or_resolve",
                            "env": env,
                        },
                    },
                    start_to_close_timeout=short,
                    retry_policy=retry,
                )
                self._closed = True
                return {
                    "run_ref": self._run_ref,
                    "ticket_ref": self._ticket_ref,
                    "decision": "needs_human",
                    "status": "passed",
                    "closer": "human.approve_or_resolve",
                    "env": env,
                }

            # auto_infra → handoff kagent + allowlisted tools → verify (or escalate if unsolved)
            infra_out = await workflow.execute_activity(
                aan.handoff_infra_agent,
                {
                    "run_ref": self._run_ref,
                    "incident_ref": tracking_id,
                    "ticket_ref": self._ticket_ref,
                    "alert": alert,
                    "decision": decision,
                },
                start_to_close_timeout=short,
                retry_policy=retry,
            )
            if not infra_out.get("ok", True):
                await workflow.execute_activity(
                    aan.escalate_unsolved,
                    {
                        "run_ref": self._run_ref,
                        "ticket_ref": self._ticket_ref,
                        "channel_ref": ticket["channel_ref"],
                        "env": env,
                        "decision": decision,
                        "attempts": infra_out.get("attempts") or [],
                        "failure_reason": infra_out.get("failure_reason") or "auto_infra tools failed",
                        "verify_status": "",
                        "extra": "Agent accepted auto_infra but could not complete the fix.",
                    },
                    start_to_close_timeout=short,
                    retry_policy=retry,
                )
                await workflow.wait_condition(lambda: self._approved or self._resolved or self._closed)
                await workflow.execute_activity(
                    acts.mark_run_status,
                    {
                        "run_ref": self._run_ref,
                        "status": "passed",
                        "summary": {
                            "ticket_ref": self._ticket_ref,
                            "decision": "auto_infra",
                            "escalated": True,
                            "closer": "auto_infra.unsolved.human",
                            "failure_reason": infra_out.get("failure_reason"),
                            "env": env,
                        },
                    },
                    start_to_close_timeout=short,
                    retry_policy=retry,
                )
                self._closed = True
                return {
                    "run_ref": self._run_ref,
                    "ticket_ref": self._ticket_ref,
                    "decision": "auto_infra",
                    "status": "passed",
                    "escalated": True,
                    "closer": "auto_infra.unsolved.human",
                    "failure_reason": infra_out.get("failure_reason"),
                    "env": env,
                }

            await workflow.execute_activity(
                aan.write_resolution_note,
                {
                    "ticket_ref": self._ticket_ref,
                    "decision": decision,
                    "actions_ran": infra_out.get("actions_ran") or [],
                    "env": env,
                },
                start_to_close_timeout=short,
                retry_policy=retry,
            )
            return await self._verify_and_close(
                tracking_id=tracking_id,
                retry=retry,
                short=short,
                verify_timeout=verify_timeout,
                closer_prefix="auto_infra",
                decision=decision,
                channel_ref=ticket["channel_ref"],
                prior_attempts=infra_out.get("attempts") or [],
                env=env,
                alert=alert,
            )

        # Legacy path: wait resolve → infra mark_fixed → verify
        await workflow.wait_condition(lambda: self._resolved or self._closed)
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
        self._decision = "legacy"
        return await self._verify_and_close(
            tracking_id=tracking_id,
            retry=retry,
            short=short,
            verify_timeout=verify_timeout,
            closer_prefix="legacy",
            env=env,
            alert=alert,
            channel_ref=ticket["channel_ref"],
        )
