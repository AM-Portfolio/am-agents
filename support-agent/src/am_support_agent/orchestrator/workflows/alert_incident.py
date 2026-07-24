"""AlertIncident workflow — visible lifecycle from evidence through verified recovery."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from am_support_agent.orchestrator.activities.incident import (
        apply_alert_silence,
        assign_ticket,
        check_parity,
        close_ticket,
        comment_ticket,
        create_ticket,
        evaluate_learning,
        evaluate_recovery_activity,
        execute_actions,
        extract_remediation_candidate,
        intelligence_gate,
        normalize_alert,
        notify_firing,
        notify_resolved,
        parse_alert_feedback,
        persist_episode_activity,
        plan_investigation,
        propose_known_fix,
        query_logs,
        query_metrics,
        record_hitl,
        record_outcome_feedback,
        resolve_owner,
        retrieve_memory,
        verify_logs,
        verify_metrics,
    )
    from am_support_agent.orchestrator.activities.telemetry import (
        finalize_run,
        persist_lifecycle,
        record_event,
    )
    from am_support_agent.orchestrator.hitl import (
        SIGNAL_ALERT_REFIRED,
        SIGNAL_ALERT_RESOLVED,
        SIGNAL_APPROVE,
        SIGNAL_APPROVE_INVESTIGATION,
        SIGNAL_APPROVE_KNOWN_FIX,
        SIGNAL_APPROVE_SILENCE,
        SIGNAL_FEEDBACK,
        HitlState,
    )


_ACTIVITY_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=10,
)

_MAX_REFIRES = 20
_MAX_VERIFY_ROUNDS = 10
_RECOVERY_STABILITY_SECONDS = 60


@workflow.defn(name="AlertIncidentWorkflow")
class AlertIncidentWorkflow:
    """Long-running firing → verify → close lifecycle; parity gated."""

    def __init__(self) -> None:
        self._hitl = HitlState()
        self._tracking_id: str = ""
        self._temporal_run_id: str = ""
        self._phase: str = "init"
        self._steps: dict[str, Any] = {}
        self._state: dict[str, Any] = {}
        self._refire_count: int = 0
        self._verify_rounds: int = 0
        self._event_seq: int = 0

    @workflow.signal(name=SIGNAL_ALERT_RESOLVED)
    async def alert_resolved(self) -> None:
        self._hitl.apply_signal(SIGNAL_ALERT_RESOLVED)

    @workflow.signal(name=SIGNAL_ALERT_REFIRED)
    async def alert_refired(self) -> None:
        self._hitl.apply_signal(SIGNAL_ALERT_REFIRED)

    @workflow.signal(name=SIGNAL_APPROVE)
    async def approve(self, payload: dict[str, Any] | None = None) -> None:
        self._hitl.apply_signal(SIGNAL_APPROVE, payload)

    @workflow.signal(name=SIGNAL_APPROVE_INVESTIGATION)
    async def approve_investigation(self, payload: dict[str, Any] | None = None) -> None:
        self._hitl.apply_signal(SIGNAL_APPROVE_INVESTIGATION, payload)

    @workflow.signal(name=SIGNAL_APPROVE_KNOWN_FIX)
    async def approve_known_fix(self, payload: dict[str, Any] | None = None) -> None:
        self._hitl.apply_signal(SIGNAL_APPROVE_KNOWN_FIX, payload)

    @workflow.signal(name=SIGNAL_APPROVE_SILENCE)
    async def approve_silence(self, payload: dict[str, Any] | None = None) -> None:
        self._hitl.apply_signal(SIGNAL_APPROVE_SILENCE, payload)

    @workflow.signal(name=SIGNAL_FEEDBACK)
    async def alert_feedback(self, payload: dict[str, Any] | None = None) -> None:
        self._hitl.apply_signal(SIGNAL_FEEDBACK, payload)

    @workflow.query
    def status(self) -> dict[str, Any]:
        return {
            "tracking_id": self._tracking_id,
            "phase": self._phase,
            "module": "support-agent",
            "steps": self._steps,
            "state": {
                k: self._state.get(k)
                for k in (
                    "episode_id",
                    "decision",
                    "work_item",
                    "owner",
                    "known_fix",
                    "silence",
                    "learned_fix",
                )
                if k in self._state
            },
            "refire_count": self._refire_count,
            "verify_rounds": self._verify_rounds,
            **self._hitl.as_dict(),
        }

    async def _act(self, fn: Any, payload: dict[str, Any], *, timeout_s: int = 120) -> dict[str, Any]:
        return await workflow.execute_activity(
            fn,
            payload,
            start_to_close_timeout=timedelta(seconds=timeout_s),
            retry_policy=_ACTIVITY_RETRY,
        )

    async def _emit(self, event_name: str, **fields: Any) -> None:
        """Best-effort durable telemetry; failures must not block incident handling."""
        self._event_seq += 1
        work_item = self._state.get("work_item") or {}
        ticket_ref = ""
        if isinstance(work_item, dict):
            ticket_ref = str(
                work_item.get("work_item_ref") or work_item.get("id") or ""
            )
        payload = {
            "event_name": event_name,
            "phase": self._phase,
            "workflow_id": f"alert-incident-{self._tracking_id}",
            "workflow_run_id": self._temporal_run_id,
            "run_ref": str(self._state.get("run_ref") or ""),
            "tracking_id": self._tracking_id,
            "episode_id": str(self._state.get("episode_id") or ""),
            "ticket_ref": ticket_ref,
            "sequence": self._event_seq,
            "environment": str(
                (self._state.get("alert") or {}).get("env")
                or (self._state.get("alert") or {}).get("environment")
                or ""
            ),
            **fields,
        }
        try:
            await self._act(record_event, payload, timeout_s=30)
        except Exception:  # noqa: BLE001 — telemetry must not fail the incident
            pass

    async def _finalize(self, domain_status: str, **extra: Any) -> None:
        work_item = self._state.get("work_item") or {}
        ticket_ref = ""
        if isinstance(work_item, dict):
            ticket_ref = str(
                work_item.get("work_item_ref") or work_item.get("id") or ""
            )
        try:
            await self._act(
                finalize_run,
                {
                    "run_ref": str(self._state.get("run_ref") or ""),
                    "domain_status": domain_status,
                    "phase": self._phase,
                    "workflow_id": f"alert-incident-{self._tracking_id}",
                    "tracking_id": self._tracking_id,
                    "episode_id": str(self._state.get("episode_id") or ""),
                    "ticket_ref": ticket_ref,
                    "approval_purpose": str(
                        (self._state.get("human_required") or {}).get("approval_purpose")
                        or ""
                    ),
                    "side_effects": self._state.get("side_effects") or {},
                    "steps": self._steps,
                    "state": {
                        "alert": self._state.get("alert") or {},
                        "work_item": work_item,
                        "side_effects": self._state.get("side_effects") or {},
                        "human_required": self._state.get("human_required") or {},
                        "similar_incident_ids": self._state.get("similar_incident_ids")
                        or [],
                        "known_fix": self._state.get("known_fix")
                        or self._state.get("proposed_known_fix")
                        or {},
                    },
                    "sequence": self._event_seq + 1,
                    **extra,
                },
                timeout_s=30,
            )
        except Exception:  # noqa: BLE001
            pass

    async def _persist_lifecycle(self, *, final_status: str = "open") -> None:
        """Best-effort ticket/agent/final status snapshot for Grafana tables."""
        try:
            await self._act(
                persist_lifecycle,
                {
                    "run_ref": str(
                        self._state.get("run_ref") or self._tracking_id or ""
                    ),
                    "tracking_id": self._tracking_id,
                    "workflow_id": f"alert-incident-{self._tracking_id}",
                    "phase": self._phase,
                    "final_status": final_status,
                    "steps": self._steps,
                    "state": {
                        "alert": self._state.get("alert") or {},
                        "work_item": self._state.get("work_item") or {},
                        "side_effects": self._state.get("side_effects") or {},
                        "human_required": self._state.get("human_required") or {},
                        "similar_incident_ids": self._state.get("similar_incident_ids")
                        or [],
                        "known_fix": self._state.get("known_fix")
                        or self._state.get("proposed_known_fix")
                        or {},
                        "tracking_id": self._tracking_id,
                        "workflow_id": f"alert-incident-{self._tracking_id}",
                        "temporal_run_id": self._temporal_run_id,
                        "run_id": self._temporal_run_id,
                    },
                },
                timeout_s=30,
            )
        except Exception:  # noqa: BLE001
            pass

    async def _handle_pending_feedback(self) -> None:
        fb = self._hitl.consume_feedback()
        if not fb:
            return
        self._phase = "parse_alert_feedback"
        parsed = await self._act(
            parse_alert_feedback,
            {
                "tracking_id": self._tracking_id,
                "alert": self._state.get("alert") or {},
                "feedback": fb,
            },
            timeout_s=30,
        )
        self._steps["parse_alert_feedback"] = parsed
        request = parsed.get("request") or {}
        if request.get("kind") == "silence" and parsed.get("needs_approval"):
            self._phase = "awaiting_silence_approval"
            self._hitl.silence_approved = False
            await workflow.wait_condition(lambda: self._hitl.silence_waiting_satisfied())
            if self._hitl.silence_approved:
                applied = await self._act(
                    apply_alert_silence,
                    {
                        "tracking_id": self._tracking_id,
                        "approved": True,
                        "request": request,
                        "work_item": self._state.get("work_item"),
                        "episode_id": self._state.get("episode_id"),
                    },
                )
                self._steps["apply_alert_silence"] = applied
                self._state["silence"] = applied.get("silence")
                await self._act(
                    record_hitl,
                    {
                        "tracking_id": self._tracking_id,
                        "episode_id": self._state.get("episode_id"),
                        "hitl": self._hitl.as_dict(),
                    },
                    timeout_s=30,
                )
        elif request.get("kind") == "disable_candidate":
            self._steps["disable_candidate"] = request

    async def _gather_evidence(self, *, recovery: bool = False) -> list[dict[str, Any]]:
        alert = dict(self._state.get("alert") or {})
        metrics_fn = verify_metrics if recovery else query_metrics
        logs_fn = verify_logs if recovery else query_logs
        metrics_fut = workflow.start_activity(
            metrics_fn,
            {"tracking_id": self._tracking_id, "alert": alert, "recovery": recovery},
            start_to_close_timeout=timedelta(seconds=120),
            retry_policy=_ACTIVITY_RETRY,
        )
        logs_fut = workflow.start_activity(
            logs_fn,
            {"tracking_id": self._tracking_id, "alert": alert, "recovery": recovery},
            start_to_close_timeout=timedelta(seconds=120),
            retry_policy=_ACTIVITY_RETRY,
        )
        metrics = await metrics_fut
        logs = await logs_fut
        key = "verify" if recovery else "observe"
        self._steps[f"{key}_metrics"] = metrics
        self._steps[f"{key}_logs"] = logs
        return [metrics.get("observation") or {}, logs.get("observation") or {}]

    async def _ticket_and_notify(
        self,
        actions: list[dict[str, Any]],
        *,
        comment_body: str | None = None,
    ) -> None:
        alert = dict(self._state.get("alert") or {})
        owner = await self._act(
            resolve_owner, {"tracking_id": self._tracking_id, "alert": alert}
        )
        self._steps["resolve_owner"] = owner
        self._state["owner"] = owner.get("owner")

        created = await self._act(
            create_ticket,
            {"tracking_id": self._tracking_id, "alert": alert},
        )
        self._steps["create_ticket"] = created
        create_ok = bool(created.get("ok", True)) and not created.get("error")
        await self._emit(
            "incident.ticket.created" if create_ok else "incident.ticket.create.failed",
            status="running" if create_ok else "partial",
            outcome="unknown" if create_ok else "partial",
            ticket_operation="create",
            labels={
                "ticket_operation": "create",
                "result": "success" if create_ok else "failure",
            },
            attributes={"error": str(created.get("error") or "")[:200]},
        )
        self._state["side_effects"] = {
            **(self._state.get("side_effects") or {}),
            "ticket_create": "ok" if create_ok else "failed",
            "ticket_status": "created" if create_ok else "create_failed",
        }

        assigned = await self._act(
            assign_ticket,
            {
                "tracking_id": self._tracking_id,
                "work_item": created.get("work_item"),
                "owner": owner.get("owner"),
            },
        )
        self._steps["assign_ticket"] = assigned
        self._state["work_item"] = assigned.get("work_item") or created.get("work_item")
        self._state["side_effects"] = {
            **(self._state.get("side_effects") or {}),
            "ticket_status": "assigned"
            if create_ok
            else str((self._state.get("side_effects") or {}).get("ticket_status") or "none"),
        }

        if actions:
            executed = await self._act(
                execute_actions,
                {"tracking_id": self._tracking_id, "actions": actions},
            )
            self._steps["execute_actions"] = executed
            self._state["executed_actions"] = executed.get("actions") or []

        notify = await self._act(
            notify_firing,
            {
                "tracking_id": self._tracking_id,
                "owner": self._state.get("owner"),
            },
        )
        self._steps["notify_firing"] = notify
        notify_ok = bool(notify.get("ok", True)) and not notify.get("error")
        self._state["side_effects"] = {
            **(self._state.get("side_effects") or {}),
            "chat_notify": "ok" if notify_ok else "failed",
            "mail_notify": "n/a",
        }

        comment = await self._act(
            comment_ticket,
            {
                "tracking_id": self._tracking_id,
                "work_item": self._state.get("work_item"),
                "body": comment_body or f"Investigation started for {self._tracking_id}",
                "idempotency_key": f"{self._tracking_id}:wi-comment-start",
            },
        )
        self._steps["comment_ticket"] = comment
        await self._persist_lifecycle(final_status="open")

    async def _handoff_to_human(
        self,
        *,
        reason: str,
        approval_purpose: str,
    ) -> dict[str, Any]:
        """Assign an open ticket to a human and complete this workflow run."""
        self._state["human_required"] = {
            "reason": reason,
            "approval_purpose": approval_purpose,
        }
        await self._ticket_and_notify(
            [],
            comment_body=(
                f"Human action required for {self._tracking_id}. "
                f"Purpose: {approval_purpose}. Reason: {reason}"
            ),
        )
        await self._persist(outcome="human_required", actions=[])
        recorded = await self._act(
            record_hitl,
            {
                "tracking_id": self._tracking_id,
                "episode_id": self._state.get("episode_id"),
                "hitl": {
                    **self._hitl.as_dict(),
                    "required": True,
                    "reason": reason,
                    "approval_purpose": approval_purpose,
                },
            },
            timeout_s=30,
        )
        self._steps["record_hitl"] = recorded
        self._phase = "human_handoff_complete"
        await self._emit(
            "incident.hitl.required",
            status="needs_human",
            outcome="human_handoff",
            terminal=True,
            labels={"approval_purpose": approval_purpose, "result": "success"},
            attributes={"reason": reason[:200]},
        )
        await self._finalize("human_required")
        return {
            "status": "human_required",
            "tracking_id": self._tracking_id,
            "phase": self._phase,
            "steps": self._steps,
            "owner": self._state.get("owner"),
            "work_item": self._state.get("work_item"),
            "episode_id": self._state.get("episode_id"),
            "approval_purpose": approval_purpose,
            "reason": reason,
            "hitl": self._hitl.as_dict(),
        }

    async def _persist(self, *, outcome: str, actions: list[dict[str, Any]] | None = None) -> None:
        ep = await self._act(
            persist_episode_activity,
            {
                "tracking_id": self._tracking_id,
                "run_ref": self._state.get("run_ref"),
                "alert": self._state.get("alert"),
                "owner": self._state.get("owner"),
                "work_item": self._state.get("work_item"),
                "observations": self._state.get("observations") or [],
                "observe": self._state.get("observe") or [],
                "validation": self._state.get("validation"),
                "decision": self._state.get("decision"),
                "actions": actions if actions is not None else self._state.get("actions") or [],
                "similar_incident_ids": self._state.get("similar_incident_ids"),
                "similar_summaries": self._state.get("similar_summaries"),
                "catalog_refs": self._state.get("catalog_refs"),
                "policy": self._state.get("policy"),
                "known_fix": self._state.get("known_fix"),
                "outcome": outcome,
            },
        )
        self._steps["persist_episode"] = ep
        self._state["episode_id"] = ep.get("episode_id")

    async def _close_if_recovered(self, sample_batches: list[list[dict[str, Any]]]) -> bool:
        recovery = await self._act(
            evaluate_recovery_activity,
            {
                "tracking_id": self._tracking_id,
                "alert": self._state.get("alert"),
                "policy": self._state.get("policy"),
                "sample_batches": sample_batches,
            },
            timeout_s=30,
        )
        self._steps["evaluate_recovery"] = recovery
        if not recovery.get("recovered"):
            return False

        closed = await self._act(
            close_ticket,
            {
                "tracking_id": self._tracking_id,
                "work_item": self._state.get("work_item"),
                "recovered": True,
            },
        )
        self._steps["close_ticket"] = closed
        if closed.get("work_item"):
            self._state["work_item"] = closed["work_item"]
        close_ok = bool(closed.get("ok", True)) and not closed.get("error")
        if not close_ok:
            await self._emit(
                "incident.ticket.close.failed",
                status="partial",
                outcome="partial",
                ticket_operation="close",
                labels={"ticket_operation": "close", "result": "failure"},
                attributes={"error": str(closed.get("error") or "close_failed")[:200]},
            )
            self._state["side_effects"] = {
                **(self._state.get("side_effects") or {}),
                "ticket_close": "failed",
            }
            # Soft-failure honesty: do not claim recovered if close failed.
            return False

        resolved_notify = await self._act(
            notify_resolved,
            {
                "tracking_id": self._tracking_id,
                "owner": self._state.get("owner"),
                "recovered": True,
            },
        )
        self._steps["notify_resolved"] = resolved_notify
        notify_ok = bool(resolved_notify.get("ok", True)) and not resolved_notify.get(
            "error"
        )
        self._state["side_effects"] = {
            **(self._state.get("side_effects") or {}),
            "ticket_close": "ok",
            "notify_resolved": "ok" if notify_ok else "failed",
        }

        feedback = await self._act(
            record_outcome_feedback,
            {
                "tracking_id": self._tracking_id,
                "episode_id": self._state.get("episode_id"),
                "outcome": "recovered",
                "recovered": True,
                "evidence": sample_batches[-1] if sample_batches else [],
            },
            timeout_s=30,
        )
        self._steps["record_outcome_feedback"] = feedback

        learned = await self._act(
            extract_remediation_candidate,
            {
                "tracking_id": self._tracking_id,
                "episode_id": self._state.get("episode_id"),
                "alert": self._state.get("alert"),
                "policy": self._state.get("policy"),
                "actions": self._state.get("executed_actions")
                or self._state.get("actions")
                or [],
            },
            timeout_s=30,
        )
        self._steps["extract_remediation_candidate"] = learned
        self._state["learned_fix"] = learned.get("candidate")

        learning = await self._act(
            evaluate_learning,
            {
                "tracking_id": self._tracking_id,
                "episode_id": self._state.get("episode_id"),
            },
            timeout_s=30,
        )
        self._steps["evaluate_learning"] = learning
        await self._emit(
            "incident.ticket.closed",
            status="passed",
            outcome="recovered",
            ticket_operation="close",
            labels={"ticket_operation": "close", "result": "success"},
            terminal=False,
        )
        return True

    @workflow.run
    async def run(self, input: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(input or {})
        # Continue-As-New may pass compact prior state.
        prior = dict(payload.get("_continued") or {})
        self._tracking_id = str(
            payload.get("tracking_id") or prior.get("tracking_id") or workflow.info().workflow_id
        )
        try:
            self._temporal_run_id = str(workflow.info().run_id or "")
        except Exception:  # noqa: BLE001
            self._temporal_run_id = str(prior.get("temporal_run_id") or "")
        self._refire_count = int(prior.get("refire_count") or 0)
        self._verify_rounds = int(prior.get("verify_rounds") or 0)
        # Restore prior state first, then stamp ids so continue-as-new cannot wipe run_id.
        self._state = dict(prior.get("state") or {})
        self._steps = dict(prior.get("steps") or {})
        self._state["tracking_id"] = self._tracking_id
        self._state["workflow_id"] = f"alert-incident-{self._tracking_id}"
        if self._temporal_run_id:
            self._state["temporal_run_id"] = self._temporal_run_id
            self._state["run_id"] = self._temporal_run_id
        if payload.get("run_ref") and not self._state.get("run_ref"):
            self._state["run_ref"] = payload.get("run_ref")

        await self._emit(
            "agent.work.started",
            status="running",
            outcome="unknown",
            attributes={"continued": bool(prior)},
        )

        self._phase = "check_parity"
        parity = await self._act(
            check_parity, {"tracking_id": self._tracking_id}, timeout_s=30
        )
        self._steps["check_parity"] = parity
        if parity.get("gated"):
            self._phase = "gated"
            await self._finalize("gated")
            return {
                "status": "gated",
                "tracking_id": self._tracking_id,
                "steps": self._steps,
                "hitl": self._hitl.as_dict(),
            }

        if not self._state.get("alert"):
            self._phase = "normalize_alert"
            norm = await self._act(
                normalize_alert,
                {
                    "tracking_id": self._tracking_id,
                    "run_ref": str(payload.get("run_ref") or self._tracking_id),
                    "alert": dict(payload.get("alert") or {}),
                },
                timeout_s=30,
            )
            self._steps["normalize_alert"] = norm
            self._state["alert"] = norm.get("alert") or {}
            self._state["run_ref"] = norm.get("run_ref")
            self._state["policy"] = norm.get("policy")

            self._phase = "retrieve_memory"
            mem = await self._act(
                retrieve_memory,
                {
                    "tracking_id": self._tracking_id,
                    "alert": self._state["alert"],
                    "policy": self._state.get("policy"),
                },
                timeout_s=60,
            )
            self._steps["retrieve_memory"] = mem
            self._state["similar_incident_ids"] = mem.get("similar_incident_ids")
            self._state["similar_summaries"] = mem.get("similar_summaries")
            self._state["catalog_refs"] = mem.get("catalog_refs")
            self._state["known_fix"] = mem.get("known_fix")

            self._phase = "query_evidence"
            observations = await self._gather_evidence(recovery=False)
            self._state["observations"] = observations

            self._phase = "intelligence_gate"
            gate = await self._act(
                intelligence_gate,
                {
                    "tracking_id": self._tracking_id,
                    "alert": self._state["alert"],
                    "observations": observations,
                },
                timeout_s=30,
            )
            self._steps["intelligence_gate"] = gate
            self._state["validation"] = gate.get("validation")
            self._state["decision"] = (gate.get("decision") or {}).get("decision")
            self._state["policy"] = gate.get("policy") or self._state.get("policy")

            if gate.get("stop"):
                await self._persist(outcome="not_confirmed", actions=[])
                self._phase = "not_confirmed"
                await self._emit(
                    "incident.not_confirmed",
                    status="passed",
                    outcome="not_confirmed",
                    terminal=True,
                )
                await self._finalize("not_confirmed")
                return {
                    "status": "not_confirmed",
                    "tracking_id": self._tracking_id,
                    "steps": self._steps,
                    "episode_id": self._state.get("episode_id"),
                }

            actions: list[dict[str, Any]] = []
            if gate.get("needs_hitl"):
                decision = dict(gate.get("decision") or {})
                reasons = [
                    str(reason)
                    for reason in decision.get("reasons") or []
                    if str(reason).strip()
                ]
                reason = "; ".join(reasons) or "intelligence gate requires human review"
                return await self._handoff_to_human(
                    reason=reason,
                    approval_purpose="investigation",
                )

            # Known-fix vs investigation plan
            proposed = await self._act(
                propose_known_fix,
                {
                    "tracking_id": self._tracking_id,
                    "known_fix": self._state.get("known_fix"),
                },
                timeout_s=30,
            )
            self._steps["propose_known_fix"] = proposed
            if proposed.get("matched"):
                self._state["proposed_known_fix"] = proposed
                candidate = str(proposed.get("candidate_id") or "matched remediation")
                return await self._handoff_to_human(
                    reason=f"Known fix {candidate} requires approval before execution",
                    approval_purpose="known_fix",
                )
            else:
                planned = await self._act(
                    plan_investigation,
                    {"tracking_id": self._tracking_id, "alert": self._state.get("alert")},
                    timeout_s=30,
                )
                self._steps["plan_investigation"] = planned
                actions = list(planned.get("actions") or [])

            self._state["actions"] = actions
            await self._ticket_and_notify(actions)
            await self._persist(outcome="pending", actions=actions)

        # Open loop: wait for resolved / refired / feedback
        sample_batches: list[list[dict[str, Any]]] = list(
            self._state.get("recovery_batches") or []
        )
        self._phase = "awaiting_resolved_or_refired"
        await self._persist_lifecycle(final_status="open")
        while True:
            self._phase = "awaiting_resolved_or_refired"
            try:
                await workflow.wait_condition(
                    lambda: self._hitl.resolved
                    or self._hitl.refired
                    or self._hitl.pending_feedback is not None
                    or self._hitl.closed,
                    timeout=timedelta(minutes=2),
                )
            except asyncio.TimeoutError:
                # Automated fallback: check PromQL metrics for recovery before human handoff
                if await self._close_if_recovered(sample_batches):
                    self._phase = "recovered"
                    await self._persist(outcome="recovered", actions=list(self._state.get("actions") or []))
                    await self._persist_lifecycle(final_status="closed")
                    return self._build_result(recovered=True)
                return await self._handoff_to_human(
                    reason="Observation deadline (2m) reached without resolution signal; metrics remained unconfirmed.",
                    approval_purpose="investigation",
                )

            if self._hitl.pending_feedback is not None:
                await self._handle_pending_feedback()
                continue

            if self._hitl.consume_refired():
                self._refire_count += 1
                self._phase = "refired_refresh"
                sample_batches = []
                self._state["recovery_batches"] = []
                observations = await self._gather_evidence(recovery=False)
                self._state["observations"] = observations
                await self._act(
                    comment_ticket,
                    {
                        "tracking_id": self._tracking_id,
                        "work_item": self._state.get("work_item"),
                        "body": f"Alert refired ({self._refire_count}) for {self._tracking_id}",
                        "idempotency_key": f"{self._tracking_id}:refire:{self._refire_count}",
                    },
                )
                if self._refire_count >= _MAX_REFIRES:
                    self._phase = "continue_as_new"
                    workflow.continue_as_new(
                        {
                            "tracking_id": self._tracking_id,
                            "_continued": {
                                "tracking_id": self._tracking_id,
                                "refire_count": 0,
                                "verify_rounds": self._verify_rounds,
                                "state": {
                                    **{
                                        k: self._state.get(k)
                                        for k in (
                                            "alert",
                                            "run_ref",
                                            "policy",
                                            "owner",
                                            "work_item",
                                            "episode_id",
                                            "actions",
                                            "executed_actions",
                                            "decision",
                                            "validation",
                                            "known_fix",
                                        )
                                    },
                                    "recovery_batches": [],
                                },
                                "steps": {},
                            },
                        }
                    )
                continue

            if self._hitl.consume_resolved():
                self._phase = "verify_recovery"
                batch = await self._gather_evidence(recovery=True)
                sample_batches.append(batch)
                # Stability window: second observation after timer.
                await workflow.sleep(timedelta(seconds=_RECOVERY_STABILITY_SECONDS))
                batch2 = await self._gather_evidence(recovery=True)
                sample_batches.append(batch2)
                self._state["recovery_batches"] = sample_batches
                self._verify_rounds += 1

                if await self._close_if_recovered(sample_batches):
                    self._hitl.closed = True
                    self._phase = "recovered"
                    await self._emit(
                        "incident.recovered",
                        status="passed",
                        outcome="recovered",
                        terminal=True,
                    )
                    await self._finalize("recovered")
                    return {
                        "status": "recovered",
                        "tracking_id": self._tracking_id,
                        "steps": self._steps,
                        "episode_id": self._state.get("episode_id"),
                        "learned_fix": self._state.get("learned_fix"),
                        "silence": self._state.get("silence"),
                        "hitl": self._hitl.as_dict(),
                    }

                if self._verify_rounds >= _MAX_VERIFY_ROUNDS:
                    return await self._handoff_to_human(
                        reason=f"Recovery verification unconfirmed after {_MAX_VERIFY_ROUNDS} rounds; metrics remained unhealthy.",
                        approval_purpose="investigation",
                    )
                # Re-arm resolution flag so workflow re-verifies instead of hanging indefinitely
                self._hitl.resolved = True
                await workflow.sleep(timedelta(seconds=10))
                continue

            if self._hitl.closed:
                self._phase = "closed"
                await self._finalize("closed")
                return {
                    "status": "closed",
                    "tracking_id": self._tracking_id,
                    "steps": self._steps,
                    "hitl": self._hitl.as_dict(),
                }
