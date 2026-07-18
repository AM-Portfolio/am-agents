"""Temporal activities for durable agent-work telemetry + ledger finalize."""

from __future__ import annotations

import logging
from typing import Any

from am_support_agent.composition import build_runtime
from am_support_agent.observability.agent_work import AgentWorkEvent, build_event, map_domain_status
from am_support_agent.observability.metrics import get_shared_metrics
from am_support_agent.stores.telemetry_outbox import build_telemetry_outbox
from am_support_agent.stores.workflow_ledger import WorkflowRunStatus

LOG = logging.getLogger("support_agent.telemetry")


def _outbox():
    return build_telemetry_outbox()


def _label(value: Any) -> str:
    if value is None:
        return "unknown"
    raw = getattr(value, "value", value)
    text = str(raw).strip()
    return text or "unknown"


def _observe(event: AgentWorkEvent) -> None:
    metrics = get_shared_metrics()
    metrics.observe_agent_work(
        work_kind=_label(event.work_kind) or "alert_incident",
        status=_label(event.status),
        outcome=_label(event.outcome),
        event_name=_label(event.event_name) or "event",
    )
    if event.event_name == "incident.hitl.required":
        metrics.observe_agent_hitl(
            purpose=str((event.labels or {}).get("approval_purpose") or "unknown"),
            result="requested",
        )
    if "ticket" in event.event_name:
        op = str((event.labels or {}).get("ticket_operation") or "unknown")
        result = str((event.labels or {}).get("result") or "unknown")
        metrics.observe_agent_ticket(operation=op, result=result)
    try:
        metrics.set_outbox_pending(_outbox().pending_count())
    except Exception:  # noqa: BLE001
        pass


def _append_event(event: AgentWorkEvent):
    """Persist to configured outbox; fall back to memory so metrics path stays honest."""
    try:
        return _outbox().append(event)
    except Exception as exc:  # noqa: BLE001
        LOG.warning(
            "telemetry outbox append failed event=%s err=%s; using memory fallback",
            event.event_name,
            exc,
        )
        from am_support_agent.stores.telemetry_outbox import memory_telemetry_outbox

        return memory_telemetry_outbox().append(event)


try:
    from temporalio import activity
except ImportError:  # pragma: no cover

    class _ActivityStub:
        @staticmethod
        def defn(fn=None, *, name: str = ""):
            def wrap(f):
                return f

            return wrap if fn is None else wrap(fn)

    activity = _ActivityStub()  # type: ignore


@activity.defn(name="support_agent.telemetry.record_event")
async def record_event(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist one agent-work event to the outbox (idempotent by dedupe_key)."""
    body = dict(payload or {})
    if "event" in body and isinstance(body["event"], dict):
        event = AgentWorkEvent(**{
            k: body["event"][k]
            for k in AgentWorkEvent.__dataclass_fields__
            if k in body["event"]
        })
    else:
        event = build_event(**body)
    rec = _append_event(event)
    try:
        _observe(event)
    except Exception:  # noqa: BLE001
        LOG.exception("telemetry metrics observe failed event=%s", event.event_name)
    return {
        "ok": True,
        "event_id": rec.event_id,
        "dedupe_key": rec.dedupe_key,
        "duplicate": rec.event_id != event.event_id
        and rec.dedupe_key == event.dedupe_key,
    }


@activity.defn(name="support_agent.telemetry.finalize_run")
async def finalize_run(payload: dict[str, Any]) -> dict[str, Any]:
    """Mark workflow ledger terminal from domain status (Phase 1 honesty)."""
    body = dict(payload or {})
    run_ref = str(body.get("run_ref") or "").strip()
    domain_status = str(body.get("domain_status") or body.get("status") or "").strip()
    if not run_ref:
        return {"ok": False, "error": "run_ref required"}
    status, outcome = map_domain_status(domain_status)
    ledger_status = {
        "needs_human": WorkflowRunStatus.NEEDS_HUMAN,
        "passed": WorkflowRunStatus.PASSED,
        "failed": WorkflowRunStatus.FAILED,
        "cancelled": WorkflowRunStatus.CANCELLED,
        "partial": WorkflowRunStatus.FAILED,
    }.get(status.value, WorkflowRunStatus.FAILED)

    runtime = build_runtime()
    summary = dict(body.get("summary") or {})
    summary["domain_status"] = domain_status
    summary["outcome"] = outcome.value
    runtime.workflow_ledger.update_run(run_ref, status=ledger_status, summary=summary)

    event = build_event(
        event_name=(
            "agent.work.completed"
            if ledger_status
            in {WorkflowRunStatus.PASSED, WorkflowRunStatus.NEEDS_HUMAN}
            else "agent.work.cancelled"
            if ledger_status == WorkflowRunStatus.CANCELLED
            else "agent.work.failed"
        ),
        status=status,
        outcome=outcome,
        phase=str(body.get("phase") or ""),
        workflow_id=str(body.get("workflow_id") or ""),
        run_ref=run_ref,
        tracking_id=str(body.get("tracking_id") or ""),
        episode_id=str(body.get("episode_id") or ""),
        ticket_ref=str(body.get("ticket_ref") or ""),
        terminal=True,
        sequence=int(body.get("sequence") or 9000),
        labels={
            "approval_purpose": str(body.get("approval_purpose") or ""),
            "result": "success"
            if ledger_status in {WorkflowRunStatus.PASSED, WorkflowRunStatus.NEEDS_HUMAN}
            else "failure",
        },
        attributes={"side_effects": body.get("side_effects") or {}},
    )
    if ledger_status == WorkflowRunStatus.NEEDS_HUMAN:
        event = build_event(
            event_name="agent.work.completed",
            status=status,
            outcome=outcome,
            phase=str(body.get("phase") or "human_handoff_complete"),
            workflow_id=str(body.get("workflow_id") or ""),
            run_ref=run_ref,
            tracking_id=str(body.get("tracking_id") or ""),
            episode_id=str(body.get("episode_id") or ""),
            ticket_ref=str(body.get("ticket_ref") or ""),
            terminal=True,
            sequence=int(body.get("sequence") or 9000),
            labels={
                "approval_purpose": str(body.get("approval_purpose") or ""),
                "result": "success",
            },
        )
    _append_event(event)
    try:
        _observe(event)
    except Exception:  # noqa: BLE001
        LOG.exception("telemetry metrics observe failed on finalize")
    return {
        "ok": True,
        "run_ref": run_ref,
        "status": ledger_status.value,
        "outcome": outcome.value,
        "event_id": event.event_id,
    }


TELEMETRY_ACTIVITIES = (record_event, finalize_run)

__all__ = ["TELEMETRY_ACTIVITIES", "finalize_run", "record_event"]
