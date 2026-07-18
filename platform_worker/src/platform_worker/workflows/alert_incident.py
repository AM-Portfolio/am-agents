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


# Per-activity policies — never apply a global maximum_attempts=3 to side effects
_LEDGER = RetryPolicy(maximum_attempts=3)
_SIDE_EFFECT = RetryPolicy(maximum_attempts=1)
_TICKET_ENSURE = RetryPolicy(maximum_attempts=2)
_LLM = RetryPolicy(maximum_attempts=2)
_INFRA = RetryPolicy(maximum_attempts=1)
_VERIFY = RetryPolicy(maximum_attempts=2)

_SHORT = timedelta(seconds=60)
_LLM_TIMEOUT = timedelta(minutes=3)
_INFRA_TIMEOUT = timedelta(minutes=5)
_VERIFY_TIMEOUT = timedelta(minutes=5)


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
        self._ticket_url: str = ""
        self._ticket_meta: dict[str, Any] = {}
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
            "ticket_url": self._ticket_url,
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

    def _notify_ctx(
        self,
        *,
        tracking_id: str,
        env: str = "",
        alert: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Shared ticket/alert/workflow fields for phase comments + notifications."""
        ctx: dict[str, Any] = {
            "run_ref": self._run_ref,
            "ticket_ref": self._ticket_ref,
            "ticket_url": self._ticket_url,
            "tracking_id": tracking_id,
            "incident_ref": tracking_id,
            "workflow_id": workflow.info().workflow_id,
            "run_id": workflow.info().run_id,
            "env": env,
            "alert": alert or {},
            "assignee_name": self._ticket_meta.get("assignee_name") or "",
            "assignee_email": self._ticket_meta.get("assignee_email") or "",
            "backup_name": self._ticket_meta.get("backup_name") or "",
            "backup_email": self._ticket_meta.get("backup_email") or "",
            "owner_source": self._ticket_meta.get("owner_source") or "",
            "channel_ref": self._ticket_meta.get("channel_ref") or "cliq:lab",
        }
        if extra:
            ctx.update(extra)
        return ctx

    async def _run_infra_actions(
        self,
        *,
        tracking_id: str,
        decision: dict[str, Any],
        env: str,
        alert: dict[str, Any],
    ) -> dict[str, Any]:
        """Handoff once, then one Temporal activity per proposed action."""
        attempts: list[dict[str, Any]] = []
        actions_ran: list[str] = []

        handoff = await workflow.execute_activity(
            aan.create_infra_handoff,
            self._notify_ctx(
                tracking_id=tracking_id,
                env=env,
                alert=alert,
                extra={"decision": decision},
            ),
            start_to_close_timeout=_INFRA_TIMEOUT,
            retry_policy=_INFRA,
        )
        if not handoff.get("ok", True):
            reason = str(handoff.get("failure_reason") or "handoff failed")
            attempts.append({"step": "handoff", "status": "failed", "error": reason})
            return {
                "ok": False,
                "handoff_ref": None,
                "actions_ran": [],
                "attempts": attempts,
                "failure_reason": reason,
                "summary": reason,
            }
        handoff_ref = handoff.get("handoff_ref")
        attempts.append(
            {
                "step": "handoff",
                "status": "ok",
                "handoff_ref": handoff_ref,
                "reused": handoff.get("reused"),
            }
        )

        proposed = list(decision.get("proposed_actions") or [])
        for index, action in enumerate(proposed):
            tool_name = str(action.get("tool_name") or "")
            out = await workflow.execute_activity(
                aan.execute_infra_action,
                self._notify_ctx(
                    tracking_id=tracking_id,
                    env=env,
                    alert=alert,
                    extra={
                        "tool_name": tool_name,
                        "args": dict(action.get("args") or {}),
                        "index": index,
                        "operation_key": f"incident:{self._run_ref}:action:{index}:{tool_name}",
                        "handoff_ref": handoff_ref,
                    },
                ),
                start_to_close_timeout=_INFRA_TIMEOUT,
                retry_policy=_INFRA,
            )
            if out.get("ok"):
                ran = list(out.get("actions_ran") or [tool_name])
                actions_ran.extend(ran)
                attempts.append(
                    {
                        "step": "tool",
                        "tool_name": tool_name,
                        "status": "ok",
                        "work_ref": out.get("work_ref"),
                        "reused": out.get("reused"),
                        "operation_key": out.get("operation_key"),
                    }
                )
                continue
            reason = str(out.get("failure_reason") or out.get("error") or "tool failed")
            attempts.append(
                {
                    "step": "tool",
                    "tool_name": tool_name,
                    "status": "failed",
                    "error": reason,
                    "operation_key": out.get("operation_key"),
                }
            )
            return {
                "ok": False,
                "handoff_ref": handoff_ref,
                "actions_ran": actions_ran,
                "attempts": attempts,
                "failure_reason": reason,
                "summary": reason,
            }

        summary = f"work_done actions={','.join(actions_ran)}"
        return {
            "ok": True,
            "handoff_ref": handoff_ref,
            "actions_ran": actions_ran,
            "attempts": attempts,
            "failure_reason": None,
            "summary": summary,
        }

    async def _verify_and_close(
        self,
        *,
        tracking_id: str,
        closer_prefix: str,
        decision: dict[str, Any] | None = None,
        channel_ref: str = "cliq:lab",
        prior_attempts: list[Any] | None = None,
        env: str = "",
        alert: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        await workflow.execute_activity(
            acts.post_incident_phase,
            self._notify_ctx(
                tracking_id=tracking_id,
                env=env,
                alert=alert,
                extra={
                    "phase": "VERIFY",
                    "status": "AUTO_INFRA",
                    "decision": (decision or {}).get("decision") or closer_prefix,
                    "reason": "Starting verify gate (Prometheus / tool-agent checks).",
                    "extras": [
                        "Prior phases (INTAKE/DECISION/HANDOFF) remain on this ticket if verify fails.",
                        f"checkpoint_key=incident:{self._run_ref}:phase:verify_start",
                    ],
                },
            ),
            start_to_close_timeout=_SHORT,
            retry_policy=_LEDGER,
        )

        spawned = await workflow.execute_activity(
            vacts.spawn_verify_run,
            {
                "parent_run_ref": self._run_ref,
                "incident_ref": tracking_id,
                "ticket_ref": self._ticket_ref,
                "workflow_id": workflow.info().workflow_id,
            },
            start_to_close_timeout=_SHORT,
            retry_policy=_VERIFY,
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
            start_to_close_timeout=_VERIFY_TIMEOUT,
            retry_policy=_VERIFY,
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

        verify_extras = [
            f"verify_run_ref={self._verify_run_ref}",
            f"verify_status={self._verify_status}",
            f"verify_reason={self._verify_reason}",
            f"evidence={self._verify_evidence!s}"[:2500],
            f"checkpoint_key=incident:{self._run_ref}:phase:verify_result",
        ]
        await workflow.execute_activity(
            acts.post_incident_phase,
            self._notify_ctx(
                tracking_id=tracking_id,
                env=env,
                alert=alert,
                extra={
                    "phase": "VERIFY",
                    "status": "RESOLVED" if verify_result["status"] == "passed" else "FAILED",
                    "decision": (decision or {}).get("decision") or closer_prefix,
                    "reason": self._verify_reason,
                    "success_summary": self._verify_reason
                    if verify_result["status"] == "passed"
                    else "",
                    "extras": verify_extras,
                },
            ),
            start_to_close_timeout=_SHORT,
            retry_policy=_LEDGER,
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
                self._notify_ctx(
                    tracking_id=tracking_id,
                    env=env,
                    alert=alert,
                    extra={
                        "channel_ref": channel_ref,
                        "decision": decision
                        or {"decision": "auto_infra", "rationale": closer_prefix},
                        "attempts": attempts,
                        "failure_reason": self._verify_reason
                        or f"verify gate failed: {verify_result['status']}",
                        "verify_status": verify_result["status"],
                        "verify_reason": self._verify_reason,
                        "verify_evidence": self._verify_evidence,
                        "extra": (
                            "Agent accepted auto path but recovery could not be verified. "
                            f"Details: {self._verify_reason}"
                        ),
                    },
                ),
                start_to_close_timeout=_LLM_TIMEOUT,
                retry_policy=_SIDE_EFFECT,
            )
            await workflow.wait_condition(lambda: self._approved or self._resolved or self._closed)
            final_status = "passed"
            closer = f"{closer_prefix}.unsolved.human"
        else:
            await workflow.execute_activity(
                aan.close_incident_ticket,
                self._notify_ctx(
                    tracking_id=tracking_id,
                    env=env,
                    alert=alert,
                    extra={
                        "channel_ref": channel_ref,
                        "closer": closer,
                        "decision": (decision or {}).get("decision") or closer_prefix,
                        "note": (
                            "Verify passed. Ticket closed by IT-Support-agent. "
                            "Grafana alert may still fire until resolved. "
                            f"Evidence: {self._verify_reason}"
                        ),
                        "verify_reason": self._verify_reason,
                        "success_summary": self._verify_reason,
                        "verify_evidence": self._verify_evidence,
                    },
                ),
                start_to_close_timeout=_SHORT,
                retry_policy=_SIDE_EFFECT,
            )

        await workflow.execute_activity(
            acts.mark_run_status,
            {
                "run_ref": self._run_ref,
                "status": final_status,
                "summary": {
                    "ticket_ref": self._ticket_ref,
                    "ticket_url": self._ticket_url,
                    "verify_run_ref": self._verify_run_ref,
                    "verify_status": self._verify_status,
                    "verify_reason": self._verify_reason,
                    "verify_evidence": self._verify_evidence,
                    "decision": self._decision,
                    "closer": closer,
                    "env": env,
                },
            },
            start_to_close_timeout=_SHORT,
            retry_policy=_LEDGER,
        )
        self._closed = True
        return {
            "run_ref": self._run_ref,
            "ticket_ref": self._ticket_ref,
            "ticket_url": self._ticket_url,
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

        run = await workflow.execute_activity(
            acts.create_incident_run,
            {
                "tracking_id": tracking_id,
                "workflow_id": workflow.info().workflow_id,
                "incident_ref": tracking_id,
                "run_ref": pre_run_ref,
            },
            start_to_close_timeout=_SHORT,
            retry_policy=_LEDGER,
        )
        self._run_ref = run["run_ref"]

        triage = await workflow.execute_activity(
            acts.triage_alert,
            {"run_ref": self._run_ref, "alert": alert},
            start_to_close_timeout=_SHORT,
            retry_policy=_LEDGER,
        )

        ticket = await workflow.execute_activity(
            acts.create_and_assign_ticket,
            {
                "run_ref": self._run_ref,
                "triage": triage,
                "alert": alert,
                "tracking_id": tracking_id,
                "incident_ref": tracking_id,
                "workflow_id": workflow.info().workflow_id,
            },
            start_to_close_timeout=_SHORT,
            retry_policy=_TICKET_ENSURE,
        )
        self._ticket_ref = ticket["ticket_ref"]
        self._ticket_url = str(ticket.get("ticket_url") or "")
        self._ticket_meta = {
            "assignee_ref": ticket.get("assignee_ref") or "",
            "assignee_name": ticket.get("assignee_name") or "",
            "assignee_email": ticket.get("assignee_email") or "",
            "backup_name": ticket.get("backup_name") or "",
            "backup_email": ticket.get("backup_email") or "",
            "owner_source": ticket.get("owner_source") or "",
            "channel_ref": ticket.get("channel_ref") or "cliq:lab",
        }
        env = str(ticket.get("env") or (alert.get("labels") or {}).get("env") or "")
        channel_ref = str(self._ticket_meta["channel_ref"])

        await workflow.execute_activity(
            acts.notify_ticket_created,
            self._notify_ctx(
                tracking_id=tracking_id,
                env=env,
                alert=alert,
                extra={
                    "channel_ref": channel_ref,
                    "title": f"[{triage['priority']}] {triage.get('summary', 'Alert')}",
                    "body": (
                        f"Ticket {ticket['ticket_ref']} assigned to "
                        f"{ticket.get('assignee_name') or ticket['assignee_ref']} env={env}"
                    ),
                },
            ),
            start_to_close_timeout=_SHORT,
            retry_policy=_SIDE_EFFECT,
        )

        if use_llm:
            decision = await workflow.execute_activity(
                aan.analyze_incident,
                {"run_ref": self._run_ref, "alert": alert},
                start_to_close_timeout=_LLM_TIMEOUT,
                retry_policy=_LLM,
            )
            self._decision = decision.get("decision")
            env = str(decision.get("env") or env)

            await workflow.execute_activity(
                aan.apply_ticket_decision,
                self._notify_ctx(
                    tracking_id=tracking_id,
                    env=env,
                    alert=alert,
                    extra={
                        "channel_ref": channel_ref,
                        "decision": decision,
                    },
                ),
                start_to_close_timeout=_SHORT,
                retry_policy=_SIDE_EFFECT,
            )

            if decision.get("decision") == "ignore":
                await workflow.execute_activity(
                    aan.close_incident_ticket,
                    self._notify_ctx(
                        tracking_id=tracking_id,
                        env=env,
                        alert=alert,
                        extra={
                            "channel_ref": channel_ref,
                            "closer": "ignore",
                            "decision": "ignore",
                            "note": "Ignored as noise. Ticket closed by IT-Support-agent.",
                        },
                    ),
                    start_to_close_timeout=_SHORT,
                    retry_policy=_SIDE_EFFECT,
                )
                self._closed = True
                return {
                    "run_ref": self._run_ref,
                    "ticket_ref": self._ticket_ref,
                    "ticket_url": self._ticket_url,
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
                            "ticket_url": self._ticket_url,
                            "decision": "needs_human",
                            "closer": "human.approve_or_resolve",
                            "env": env,
                        },
                    },
                    start_to_close_timeout=_SHORT,
                    retry_policy=_LEDGER,
                )
                self._closed = True
                return {
                    "run_ref": self._run_ref,
                    "ticket_ref": self._ticket_ref,
                    "ticket_url": self._ticket_url,
                    "decision": "needs_human",
                    "status": "passed",
                    "closer": "human.approve_or_resolve",
                    "env": env,
                }

            infra_out = await self._run_infra_actions(
                tracking_id=tracking_id,
                decision=decision,
                env=env,
                alert=alert,
            )
            if not infra_out.get("ok", True):
                await workflow.execute_activity(
                    aan.escalate_unsolved,
                    self._notify_ctx(
                        tracking_id=tracking_id,
                        env=env,
                        alert=alert,
                        extra={
                            "channel_ref": channel_ref,
                            "decision": decision,
                            "attempts": infra_out.get("attempts") or [],
                            "failure_reason": infra_out.get("failure_reason")
                            or "auto_infra tools failed",
                            "verify_status": "",
                            "extra": "Agent accepted auto_infra but could not complete the fix.",
                        },
                    ),
                    start_to_close_timeout=_LLM_TIMEOUT,
                    retry_policy=_SIDE_EFFECT,
                )
                await workflow.wait_condition(lambda: self._approved or self._resolved or self._closed)
                await workflow.execute_activity(
                    acts.mark_run_status,
                    {
                        "run_ref": self._run_ref,
                        "status": "passed",
                        "summary": {
                            "ticket_ref": self._ticket_ref,
                            "ticket_url": self._ticket_url,
                            "decision": "auto_infra",
                            "escalated": True,
                            "closer": "auto_infra.unsolved.human",
                            "failure_reason": infra_out.get("failure_reason"),
                            "env": env,
                        },
                    },
                    start_to_close_timeout=_SHORT,
                    retry_policy=_LEDGER,
                )
                self._closed = True
                return {
                    "run_ref": self._run_ref,
                    "ticket_ref": self._ticket_ref,
                    "ticket_url": self._ticket_url,
                    "decision": "auto_infra",
                    "status": "passed",
                    "escalated": True,
                    "closer": "auto_infra.unsolved.human",
                    "failure_reason": infra_out.get("failure_reason"),
                    "env": env,
                }

            await workflow.execute_activity(
                aan.write_resolution_note,
                self._notify_ctx(
                    tracking_id=tracking_id,
                    env=env,
                    alert=alert,
                    extra={
                        "decision": decision,
                        "actions_ran": infra_out.get("actions_ran") or [],
                    },
                ),
                start_to_close_timeout=_LLM_TIMEOUT,
                retry_policy=_SIDE_EFFECT,
            )
            return await self._verify_and_close(
                tracking_id=tracking_id,
                closer_prefix="auto_infra",
                decision=decision,
                channel_ref=channel_ref,
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
            start_to_close_timeout=_INFRA_TIMEOUT,
            retry_policy=_INFRA,
        )
        self._decision = "legacy"
        return await self._verify_and_close(
            tracking_id=tracking_id,
            closer_prefix="legacy",
            env=env,
            alert=alert,
            channel_ref=channel_ref,
        )
