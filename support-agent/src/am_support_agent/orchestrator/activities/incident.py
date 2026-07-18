"""AlertIncident activities — parity path uses composition + durable memory."""

from __future__ import annotations

import os
from typing import Any

from temporalio import activity

from am_support_agent.composition import build_runtime
from am_support_agent.contracts.capabilities import (
    ApprovalMetadata,
    CapabilityCall,
    DirectoryOwner,
    IdempotencyMetadata,
    ObserveEvidence,
    WorkItemRef,
)
from am_support_agent.contracts.enums import ApprovalRisk, IncidentValidationStatus
from am_support_agent.contracts.incident import IncidentEpisode, episode_id_for
from am_support_agent.intelligence import (
    ActionPlanner,
    ContextBuilder,
    EpisodeRetriever,
    IncidentValidator,
)
from am_support_agent.learning import ingest_feedback_event, persist_episode


def incident_parity_enabled() -> bool:
    return os.getenv("SUPPORT_AGENT_INCIDENT_PARITY", "").lower() in {
        "1",
        "true",
        "yes",
    }


def _gate_payload(phase: str, tracking_id: str) -> dict[str, Any]:
    return {
        "gated": True,
        "phase": phase,
        "tracking_id": tracking_id,
        "module": "support-agent",
        "task_queue": "support-agent-v2",
        "reason": (
            "AlertIncident side-effect activities are gated until "
            "SUPPORT_AGENT_INCIDENT_PARITY=true and composition root ports are ready."
        ),
        "required_ports": [
            "CapabilityClient",
            "LlmClient",
            "DocumentStore",
            "WorkflowLedger",
            "EpisodeStore",
            "Redactor",
        ],
        "legacy_reference": "platform_worker/src/platform_worker/workflows/alert_incident.py",
    }


def _work_item_from_data(data: dict[str, Any], *, provider: str = "") -> WorkItemRef:
    return WorkItemRef(
        work_item_ref=str(data.get("work_item_ref") or data.get("id") or ""),
        url=str(data.get("url") or ""),
        provider=provider or str(data.get("provider") or ""),
        status=str(data.get("status") or ""),
        assignee_ref=str(data.get("assignee_ref") or ""),
        labels=dict(data.get("labels") or {}) if isinstance(data.get("labels"), dict) else {},
        updated_at=str(data.get("updated_at") or ""),
        lock_version=str(data.get("lock_version") or ""),
        correlation_id=str(data.get("correlation_id") or ""),
    )


@activity.defn(name="support_agent.incident.bootstrap")
async def bootstrap_incident(payload: dict[str, Any]) -> dict[str, Any]:
    tracking_id = str(payload.get("tracking_id") or "")
    alert = dict(payload.get("alert") or {})
    if not incident_parity_enabled():
        return _gate_payload("bootstrap", tracking_id)

    runtime = build_runtime()
    alert = runtime.redactor.redact_dict(alert)
    cap = runtime.capability
    run_ref = str(payload.get("run_ref") or tracking_id)

    owner_res = await cap.call(
        CapabilityCall(
            capability="directory.owner.resolve",
            args={
                "service": str(alert.get("service") or ""),
                "team": str(alert.get("team") or ""),
            },
        )
    )
    owner = None
    if owner_res.ok:
        owner = DirectoryOwner.model_validate(
            {
                "assignee_ref": owner_res.data.get("assignee_ref") or "mem:user:default",
                "assignee_name": owner_res.data.get("assignee_name") or "",
                "assignee_email": owner_res.data.get("assignee_email") or "",
                "channel_ref": owner_res.data.get("channel_ref") or "cliq:lab",
                "owner_source": owner_res.data.get("owner_source") or owner_res.provider,
            }
        )

    create = await cap.call(
        CapabilityCall(
            capability="work-item.create",
            args={
                "title": str(alert.get("title") or alert.get("alertname") or tracking_id)[:255],
                "description": str(alert.get("description") or alert.get("summary") or ""),
                "priority": str(alert.get("priority") or "P3"),
                "labels": {
                    "tracking_id": tracking_id,
                    "service": str(alert.get("service") or ""),
                    "env": str(alert.get("env") or alert.get("environment") or ""),
                },
            },
            approval=ApprovalMetadata(risk=ApprovalRisk.CREATE),
            idempotency=IdempotencyMetadata(key=f"{tracking_id}:wi-create"),
        )
    )
    wi_data = dict(create.data) if create.ok else {}
    work_item = _work_item_from_data(wi_data, provider=create.provider) if create.ok else None

    if work_item and owner and owner.assignee_ref:
        await cap.call(
            CapabilityCall(
                capability="work-item.assign",
                args={
                    "work_item_ref": work_item.work_item_ref,
                    "assignee_ref": owner.assignee_ref,
                },
                approval=ApprovalMetadata(risk=ApprovalRisk.UPDATE),
                idempotency=IdempotencyMetadata(key=f"{tracking_id}:wi-assign"),
            )
        )

    if work_item:
        got = await cap.call(
            CapabilityCall(
                capability="work-item.get",
                args={"work_item_ref": work_item.work_item_ref},
            )
        )
        if got.ok:
            work_item = _work_item_from_data(got.data, provider=got.provider or create.provider)

    observe: list[ObserveEvidence] = []
    for kind, capability in (
        ("metrics", "observe.metrics.query"),
        ("logs", "observe.logs.query"),
    ):
        res = await cap.call(
            CapabilityCall(
                capability=capability,
                args={
                    "query_ref": str(alert.get("service") or tracking_id),
                    "service": str(alert.get("service") or ""),
                },
            )
        )
        observe.append(
            ObserveEvidence(
                kind=kind,
                query_ref=str(alert.get("service") or tracking_id),
                status="ok" if res.ok else "error",
                summary=str((res.data or {}).get("summary") or capability),
                ref=f"{capability}:{tracking_id}",
                data=dict(res.data or {}),
                freshness_at=runtime.clock.now_iso(),
            )
        )

    retriever = EpisodeRetriever(runtime.episodes)
    similar_eps = retriever.similar_episodes(alert, limit=5)
    similar = [ep.episode_id for ep in similar_eps]
    similar_summaries = retriever.summaries(alert, limit=5)
    catalog_refs = []
    try:
        summary = runtime.catalog.summary()
        if summary.get("available"):
            catalog_refs.append(f"catalog:{summary.get('root')}")
    except Exception:  # noqa: BLE001
        pass

    ctx = ContextBuilder(clock=runtime.clock).build(
        tracking_id=tracking_id,
        run_ref=run_ref,
        alert=alert,
        work_item=work_item,
        owner=owner,
        observe=observe,
        similar_incident_ids=similar,
        similar_summaries=similar_summaries,
        catalog_refs=catalog_refs,
    )
    validation = IncidentValidator().validate(ctx)

    if (
        validation.status == IncidentValidationStatus.NOT_CONFIRMED
        and work_item
        and work_item.work_item_ref
    ):
        await cap.call(
            CapabilityCall(
                capability="work-item.comment",
                args={
                    "work_item_ref": work_item.work_item_ref,
                    "body": "Incident not confirmed — stopping without remediation.",
                },
                approval=ApprovalMetadata(risk=ApprovalRisk.UPDATE),
                idempotency=IdempotencyMetadata(key=f"{tracking_id}:wi-not-confirmed"),
            )
        )

    actions = ActionPlanner().plan(validation=validation, ctx=ctx)
    eid = episode_id_for(tracking_id=tracking_id, run_ref=run_ref)
    outcome = "pending"
    if validation.status == IncidentValidationStatus.NOT_CONFIRMED:
        outcome = "not_confirmed"
    episode = persist_episode(
        IncidentEpisode(
            episode_id=eid,
            tracking_id=tracking_id,
            run_ref=run_ref,
            context=ctx,
            validation=validation,
            decision=validation.status.value,
            actions=actions,
            outcome=outcome,
            provenance={"module": "support-agent", "policy": validation.policy_version},
        )
    )

    return {
        "gated": False,
        "phase": "bootstrap",
        "tracking_id": tracking_id,
        "run_ref": run_ref,
        "context": ctx.model_dump(),
        "validation": validation.model_dump(),
        "actions": actions,
        "episode_id": episode.episode_id,
        "similar_summaries": similar_summaries,
        "needs_hitl": validation.status == IncidentValidationStatus.INCONCLUSIVE,
        "continue": validation.status == IncidentValidationStatus.CONFIRMED,
        "stop": validation.status == IncidentValidationStatus.NOT_CONFIRMED,
    }


@activity.defn(name="support_agent.incident.finalize")
async def finalize_incident(payload: dict[str, Any]) -> dict[str, Any]:
    """Dispatch planned actions after confirmation (or HITL approve)."""
    tracking_id = str(payload.get("tracking_id") or "")
    if not incident_parity_enabled():
        return _gate_payload("finalize", tracking_id)

    runtime = build_runtime()
    actions = list(payload.get("actions") or [])
    episode_id = str(payload.get("episode_id") or "")
    results: list[dict[str, Any]] = []
    for idx, action in enumerate(actions):
        capability = str(action.get("capability") or "")
        if not capability:
            continue
        risk = ApprovalRisk.SEND if "send" in capability else ApprovalRisk.UPDATE
        res = await runtime.capability.call(
            CapabilityCall(
                capability=capability,
                args=dict(action.get("args") or {}),
                approval=ApprovalMetadata(risk=risk),
                idempotency=IdempotencyMetadata(
                    key=f"{tracking_id}:{capability}:{idx}"
                ),
            )
        )
        results.append(
            {
                "capability": capability,
                "ok": res.ok,
                "error": res.error,
            }
        )

    outcome = "confirmed" if all(r.get("ok") for r in results) or not results else "finalize_partial"
    if episode_id:
        try:
            runtime.episodes.update_outcome(
                episode_id,
                outcome=outcome,
                verify_status="passed" if outcome == "confirmed" else "partial",
                evidence=[
                    {"kind": "finalize", "ref": r["capability"], "provenance": "capability"}
                    for r in results
                    if r.get("ok")
                ],
            )
        except KeyError:
            pass

    return {
        "gated": False,
        "phase": "finalize",
        "tracking_id": tracking_id,
        "episode_id": episode_id,
        "outcome": outcome,
        "results": results,
    }


@activity.defn(name="support_agent.incident.record_hitl")
async def record_hitl(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist HITL outcome metadata into episodic/feedback stores."""
    tracking_id = str(payload.get("tracking_id") or "")
    hitl = dict(payload.get("hitl") or {})
    episode_id = str(payload.get("episode_id") or "")
    outcome = "hitl_recorded"
    if hitl.get("approved"):
        outcome = "hitl_approved"
    elif hitl.get("resolved"):
        outcome = "hitl_resolved"
    elif hitl.get("closed"):
        outcome = "inconclusive_closed"

    fb = ingest_feedback_event(
        {
            "episode_id": episode_id,
            "tracking_id": tracking_id,
            "kind": "hitl",
            "rating": outcome,
            "notes": "hitl signal received",
            "outcome": outcome,
            "idempotency_key": f"{tracking_id}:hitl:{episode_id}",
            "payload": hitl,
        }
    )
    return {
        "gated": False,
        "phase": "hitl",
        "tracking_id": tracking_id,
        "hitl": hitl,
        "feedback": fb,
        "outcome": outcome,
        "module": "support-agent",
    }
