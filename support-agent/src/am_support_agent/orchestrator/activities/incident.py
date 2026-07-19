"""AlertIncident activities — visible lifecycle steps + durable memory."""

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
from am_support_agent.contracts.incident import (
    IncidentEpisode,
    IncidentValidation,
    episode_id_for,
)
from am_support_agent.intelligence import (
    ActionPlanner,
    ContextBuilder,
    EpisodeRetriever,
)
from am_support_agent.intelligence.evidence_policy import (
    classify_from_evidence,
    evaluate_observation,
    evaluate_recovery,
    select_policy,
)
from am_support_agent.learning import ingest_feedback_event, persist_episode
from am_support_agent.learning.offline import evaluate_episode
from am_support_agent.orchestrator.queue import resolve_task_queue
from am_support_agent.stores.remediation import (
    classify_effect,
    extract_remediation_steps,
    find_matching_candidate,
    remediation_store_enabled,
    step_hash_for,
    upsert_candidate,
)
from am_support_agent.contracts.incident import RemediationCandidate


def incident_parity_enabled() -> bool:
    return os.getenv("SUPPORT_AGENT_INCIDENT_PARITY", "").lower() in {
        "1",
        "true",
        "yes",
    }


def _gate_payload(phase: str, tracking_id: str) -> dict[str, Any]:
    try:
        queue = resolve_task_queue(require_env_suffix=False)
    except Exception:  # noqa: BLE001
        queue = "support-agent-v2-dev"
    return {
        "gated": True,
        "phase": phase,
        "tracking_id": tracking_id,
        "module": "support-agent",
        "task_queue": queue,
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
    # tool-agent may nest domain fields under data={ok, provider, data:{...}}
    inner = data.get("data")
    if isinstance(inner, dict) and (
        inner.get("work_item_ref") or inner.get("id") or inner.get("url")
    ):
        data = inner
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


def _labels(alert: dict[str, Any]) -> dict[str, str]:
    raw = alert.get("labels") if isinstance(alert.get("labels"), dict) else {}
    return {str(k): str(v) for k, v in raw.items()}


def _promote_alert_fields(alert: dict[str, Any]) -> dict[str, Any]:
    out = dict(alert)
    labels = _labels(out)
    out.setdefault("service", labels.get("service") or labels.get("application") or out.get("service") or "")
    out.setdefault(
        "env",
        labels.get("env")
        or labels.get("environment")
        or out.get("env")
        or out.get("environment")
        or "",
    )
    out.setdefault("team", labels.get("team") or out.get("team") or "")
    out.setdefault(
        "alertname",
        labels.get("alertname") or out.get("alertname") or out.get("title") or "",
    )
    out.setdefault("fingerprint", out.get("fingerprint") or labels.get("fingerprint") or "")
    out["labels"] = labels
    return out


async def _query_observe(
    *,
    kind: str,
    capability: str,
    alert: dict[str, Any],
    tracking_id: str,
    recovery: bool = False,
) -> dict[str, Any]:
    runtime = build_runtime()
    policy = select_policy(alert)
    res = await runtime.capability.call(
        CapabilityCall(
            capability=capability,
            args={
                "query_ref": str(alert.get("service") or tracking_id),
                "service": str(alert.get("service") or ""),
                "env": str(alert.get("env") or ""),
                "fingerprint": str(alert.get("fingerprint") or ""),
                "recovery": recovery,
            },
        )
    )
    data = dict(res.data or {})
    obs = evaluate_observation(
        policy=policy,
        kind=kind,
        transport_ok=bool(res.ok),
        data=data,
        observed_at=runtime.clock.now_iso(),
    )
    return {
        "gated": False,
        "phase": f"query_{kind}",
        "tracking_id": tracking_id,
        "observation": obs.model_dump(),
        "observe_evidence": ObserveEvidence(
            kind=kind,
            query_ref=str(alert.get("service") or tracking_id),
            status="ok" if res.ok else "error",
            summary=obs.summary,
            ref=f"{capability}:{tracking_id}",
            data=data,
            freshness_at=obs.observed_at,
        ).model_dump(),
    }


@activity.defn(name="support_agent.incident.check_parity")
async def check_parity(payload: dict[str, Any]) -> dict[str, Any]:
    tracking_id = str(payload.get("tracking_id") or "")
    if not incident_parity_enabled():
        return _gate_payload("check_parity", tracking_id)
    return {"gated": False, "phase": "check_parity", "tracking_id": tracking_id}


@activity.defn(name="support_agent.incident.normalize_alert")
async def normalize_alert(payload: dict[str, Any]) -> dict[str, Any]:
    tracking_id = str(payload.get("tracking_id") or "")
    if not incident_parity_enabled():
        return _gate_payload("normalize_alert", tracking_id)
    runtime = build_runtime()
    alert = _promote_alert_fields(runtime.redactor.redact_dict(dict(payload.get("alert") or {})))
    policy = select_policy(alert)
    return {
        "gated": False,
        "phase": "normalize_alert",
        "tracking_id": tracking_id,
        "run_ref": str(payload.get("run_ref") or tracking_id),
        "alert": alert,
        "policy": policy.model_dump(),
    }


@activity.defn(name="support_agent.incident.retrieve_memory")
async def retrieve_memory(payload: dict[str, Any]) -> dict[str, Any]:
    tracking_id = str(payload.get("tracking_id") or "")
    if not incident_parity_enabled():
        return _gate_payload("retrieve_memory", tracking_id)
    runtime = build_runtime()
    alert = dict(payload.get("alert") or {})
    retriever = EpisodeRetriever(runtime.episodes)
    similar_eps = retriever.similar_episodes(alert, limit=5)
    similar = [ep.episode_id for ep in similar_eps]
    similar_summaries = retriever.summaries(alert, limit=5)
    known = None
    if remediation_store_enabled():
        known = find_matching_candidate(
            service=str(alert.get("service") or ""),
            env=str(alert.get("env") or ""),
            fingerprint=str(alert.get("fingerprint") or ""),
            policy_id=str((payload.get("policy") or {}).get("policy_id") or ""),
        )
    catalog_refs: list[str] = []
    try:
        summary = runtime.catalog.summary()
        if summary.get("available"):
            catalog_refs.append(f"catalog:{summary.get('root')}")
    except Exception:  # noqa: BLE001
        pass
    return {
        "gated": False,
        "phase": "retrieve_memory",
        "tracking_id": tracking_id,
        "similar_incident_ids": similar,
        "similar_summaries": similar_summaries,
        "memory_refs": list(similar),
        "catalog_refs": catalog_refs,
        "known_fix": known.model_dump() if known else None,
    }


@activity.defn(name="support_agent.incident.query_metrics")
async def query_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    tracking_id = str(payload.get("tracking_id") or "")
    if not incident_parity_enabled():
        return _gate_payload("query_metrics", tracking_id)
    return await _query_observe(
        kind="metrics",
        capability="observe.metrics.query",
        alert=dict(payload.get("alert") or {}),
        tracking_id=tracking_id,
        recovery=bool(payload.get("recovery")),
    )


@activity.defn(name="support_agent.incident.query_logs")
async def query_logs(payload: dict[str, Any]) -> dict[str, Any]:
    tracking_id = str(payload.get("tracking_id") or "")
    if not incident_parity_enabled():
        return _gate_payload("query_logs", tracking_id)
    return await _query_observe(
        kind="logs",
        capability="observe.logs.query",
        alert=dict(payload.get("alert") or {}),
        tracking_id=tracking_id,
        recovery=bool(payload.get("recovery")),
    )


@activity.defn(name="support_agent.incident.verify_metrics")
async def verify_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    out = await query_metrics({**payload, "recovery": True})
    out["phase"] = "verify_metrics"
    return out


@activity.defn(name="support_agent.incident.verify_logs")
async def verify_logs(payload: dict[str, Any]) -> dict[str, Any]:
    out = await query_logs({**payload, "recovery": True})
    out["phase"] = "verify_logs"
    return out


@activity.defn(name="support_agent.incident.intelligence_gate")
async def intelligence_gate(payload: dict[str, Any]) -> dict[str, Any]:
    tracking_id = str(payload.get("tracking_id") or "")
    if not incident_parity_enabled():
        return _gate_payload("intelligence_gate", tracking_id)
    alert = dict(payload.get("alert") or {})
    policy = select_policy(alert)
    observations = []
    for raw in payload.get("observations") or []:
        if isinstance(raw, dict):
            from am_support_agent.contracts.incident import EvidenceObservation

            observations.append(EvidenceObservation.model_validate(raw))
    decision = classify_from_evidence(alert=alert, observations=observations, policy=policy)
    validation = IncidentValidation(
        status=IncidentValidationStatus(decision["status"]),
        confidence=float(decision.get("confidence") or 0),
        reasons=list(decision.get("reasons") or []),
        missing_evidence=list(decision.get("missing_evidence") or []),
        freshness_at=build_runtime().clock.now_iso(),
        work_item_ok=False,
        policy_version=str(decision.get("policy_version") or policy.policy_version),
    )
    return {
        "gated": False,
        "phase": "intelligence_gate",
        "tracking_id": tracking_id,
        "decision": decision,
        "validation": validation.model_dump(),
        "needs_hitl": bool(decision.get("needs_hitl")),
        "continue": bool(decision.get("continue")),
        "stop": bool(decision.get("stop")),
        "policy": policy.model_dump(),
    }


@activity.defn(name="support_agent.incident.propose_known_fix")
async def propose_known_fix(payload: dict[str, Any]) -> dict[str, Any]:
    tracking_id = str(payload.get("tracking_id") or "")
    if not incident_parity_enabled():
        return _gate_payload("propose_known_fix", tracking_id)
    known_raw = payload.get("known_fix")
    if not known_raw:
        return {
            "gated": False,
            "phase": "propose_known_fix",
            "tracking_id": tracking_id,
            "matched": False,
            "actions": [],
        }
    candidate = RemediationCandidate.model_validate(known_raw)
    if not candidate.steps:
        return {
            "gated": False,
            "phase": "propose_known_fix",
            "tracking_id": tracking_id,
            "matched": False,
            "actions": [],
        }
    actions = [
        {
            "capability": step.capability,
            "args": dict(step.args_schema),
            "effect": "remediation",
            "version": step.version,
            "risk": step.risk,
            "from_known_fix": True,
        }
        for step in candidate.steps
    ]
    return {
        "gated": False,
        "phase": "propose_known_fix",
        "tracking_id": tracking_id,
        "matched": True,
        "candidate_id": candidate.candidate_id,
        "step_hash": candidate.step_hash or step_hash_for(candidate.steps),
        "actions": actions,
        "requires_approval": True,
    }


@activity.defn(name="support_agent.incident.plan_investigation")
async def plan_investigation(payload: dict[str, Any]) -> dict[str, Any]:
    tracking_id = str(payload.get("tracking_id") or "")
    if not incident_parity_enabled():
        return _gate_payload("plan_investigation", tracking_id)
    # Notification/ticket admin are planned later; investigation plan is empty
    # until real remediation capabilities are available.
    return {
        "gated": False,
        "phase": "plan_investigation",
        "tracking_id": tracking_id,
        "actions": [],
        "matched": False,
    }


@activity.defn(name="support_agent.incident.resolve_owner")
async def resolve_owner(payload: dict[str, Any]) -> dict[str, Any]:
    tracking_id = str(payload.get("tracking_id") or "")
    if not incident_parity_enabled():
        return _gate_payload("resolve_owner", tracking_id)
    runtime = build_runtime()
    alert = dict(payload.get("alert") or {})
    owner_res = await runtime.capability.call(
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
    return {
        "gated": False,
        "phase": "resolve_owner",
        "tracking_id": tracking_id,
        "owner": owner.model_dump() if owner else None,
    }


@activity.defn(name="support_agent.incident.create_ticket")
async def create_ticket(payload: dict[str, Any]) -> dict[str, Any]:
    tracking_id = str(payload.get("tracking_id") or "")
    if not incident_parity_enabled():
        return _gate_payload("create_ticket", tracking_id)
    runtime = build_runtime()
    alert = dict(payload.get("alert") or {})
    create = await runtime.capability.call(
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
    work_item = (
        _work_item_from_data(dict(create.data), provider=create.provider)
        if create.ok
        else None
    )
    return {
        "gated": False,
        "phase": "create_ticket",
        "tracking_id": tracking_id,
        "work_item": work_item.model_dump() if work_item else None,
        "ok": bool(create.ok),
        "error": create.error,
    }


@activity.defn(name="support_agent.incident.assign_ticket")
async def assign_ticket(payload: dict[str, Any]) -> dict[str, Any]:
    tracking_id = str(payload.get("tracking_id") or "")
    if not incident_parity_enabled():
        return _gate_payload("assign_ticket", tracking_id)
    runtime = build_runtime()
    wi_raw = payload.get("work_item") or {}
    owner_raw = payload.get("owner") or {}
    if not wi_raw or not owner_raw.get("assignee_ref"):
        return {
            "gated": False,
            "phase": "assign_ticket",
            "tracking_id": tracking_id,
            "work_item": wi_raw or None,
            "skipped": True,
        }
    work_item = _work_item_from_data(dict(wi_raw))
    await runtime.capability.call(
        CapabilityCall(
            capability="work-item.assign",
            args={
                "work_item_ref": work_item.work_item_ref,
                "assignee_ref": str(owner_raw.get("assignee_ref") or ""),
                "assignee_name": str(owner_raw.get("assignee_name") or ""),
            },
            approval=ApprovalMetadata(risk=ApprovalRisk.UPDATE),
            idempotency=IdempotencyMetadata(key=f"{tracking_id}:wi-assign"),
        )
    )
    got = await runtime.capability.call(
        CapabilityCall(
            capability="work-item.get",
            args={"work_item_ref": work_item.work_item_ref},
        )
    )
    if got.ok:
        work_item = _work_item_from_data(got.data, provider=got.provider)
    # Ensure owner fields survive into lifecycle summary even when the work-item
    # provider omits assignee_name (common for fake / partial adapters).
    wi = work_item.model_dump()
    if owner_raw.get("assignee_ref") and not wi.get("assignee_ref"):
        wi["assignee_ref"] = str(owner_raw.get("assignee_ref") or "")
    if owner_raw.get("assignee_name") and not wi.get("assignee_name"):
        wi["assignee_name"] = str(owner_raw.get("assignee_name") or "")
    if owner_raw.get("assignee_email") and not wi.get("assignee_email"):
        wi["assignee_email"] = str(owner_raw.get("assignee_email") or "")
    return {
        "gated": False,
        "phase": "assign_ticket",
        "tracking_id": tracking_id,
        "work_item": wi,
        "owner": dict(owner_raw) if owner_raw else None,
        "skipped": False,
    }


@activity.defn(name="support_agent.incident.persist_episode")
async def persist_episode_activity(payload: dict[str, Any]) -> dict[str, Any]:
    tracking_id = str(payload.get("tracking_id") or "")
    if not incident_parity_enabled():
        return _gate_payload("persist_episode", tracking_id)
    runtime = build_runtime()
    run_ref = str(payload.get("run_ref") or tracking_id)
    alert = dict(payload.get("alert") or {})
    owner = None
    if payload.get("owner"):
        owner = DirectoryOwner.model_validate(payload["owner"])
    work_item = None
    if payload.get("work_item"):
        work_item = WorkItemRef.model_validate(payload["work_item"])
    observe = [
        ObserveEvidence.model_validate(o)
        for o in (payload.get("observe") or [])
        if isinstance(o, dict)
    ]
    from am_support_agent.contracts.incident import EvidenceObservation

    evidence_observations = [
        EvidenceObservation.model_validate(o)
        for o in (payload.get("observations") or [])
        if isinstance(o, dict)
    ]
    validation_raw = dict(payload.get("validation") or {})
    validation = IncidentValidation.model_validate(
        validation_raw
        or {
            "status": IncidentValidationStatus.INCONCLUSIVE.value,
            "confidence": 0.0,
        }
    )
    actions = list(payload.get("actions") or [])
    known_fix = None
    if payload.get("known_fix"):
        known_fix = RemediationCandidate.model_validate(payload["known_fix"])
    ctx = ContextBuilder(clock=runtime.clock).build(
        tracking_id=tracking_id,
        run_ref=run_ref,
        alert=alert,
        work_item=work_item,
        owner=owner,
        observe=observe,
        similar_incident_ids=list(payload.get("similar_incident_ids") or []),
        similar_summaries=list(payload.get("similar_summaries") or []),
        catalog_refs=list(payload.get("catalog_refs") or []),
    )
    ctx = ctx.model_copy(
        update={
            "evidence_observations": evidence_observations,
            "policy_id": str((payload.get("policy") or {}).get("policy_id") or ""),
            "policy_version": str((payload.get("policy") or {}).get("policy_version") or ""),
            "known_fix": known_fix,
        }
    )
    eid = episode_id_for(tracking_id=tracking_id, run_ref=run_ref)
    outcome = str(payload.get("outcome") or "pending")
    episode = persist_episode(
        IncidentEpisode(
            episode_id=eid,
            tracking_id=tracking_id,
            run_ref=run_ref,
            context=ctx,
            validation=validation,
            decision=str(payload.get("decision") or validation.status.value),
            actions=actions,
            outcome=outcome,
            provenance={
                "module": "support-agent",
                "policy": validation.policy_version,
            },
        )
    )
    return {
        "gated": False,
        "phase": "persist_episode",
        "tracking_id": tracking_id,
        "episode_id": episode.episode_id,
        "context": ctx.model_dump(),
    }


@activity.defn(name="support_agent.incident.notify_firing")
async def notify_firing(payload: dict[str, Any]) -> dict[str, Any]:
    tracking_id = str(payload.get("tracking_id") or "")
    if not incident_parity_enabled():
        return _gate_payload("notify_firing", tracking_id)
    runtime = build_runtime()
    owner = dict(payload.get("owner") or {})
    channel = str(owner.get("channel_ref") or "cliq:lab")
    body = str(
        payload.get("body")
        or f"Investigation started for {tracking_id}"
    )
    res = await runtime.capability.call(
        CapabilityCall(
            capability="chat.message.send",
            args={"channel_ref": channel, "body": body},
            approval=ApprovalMetadata(risk=ApprovalRisk.SEND),
            idempotency=IdempotencyMetadata(key=f"{tracking_id}:notify-firing"),
        )
    )
    return {
        "gated": False,
        "phase": "notify_firing",
        "tracking_id": tracking_id,
        "ok": bool(res.ok),
        "error": res.error,
        "effect": "notify",
    }


@activity.defn(name="support_agent.incident.comment_ticket")
async def comment_ticket(payload: dict[str, Any]) -> dict[str, Any]:
    tracking_id = str(payload.get("tracking_id") or "")
    if not incident_parity_enabled():
        return _gate_payload("comment_ticket", tracking_id)
    wi = dict(payload.get("work_item") or {})
    if not wi.get("work_item_ref"):
        return {
            "gated": False,
            "phase": "comment_ticket",
            "tracking_id": tracking_id,
            "skipped": True,
        }
    runtime = build_runtime()
    body = str(payload.get("body") or f"Incident update for {tracking_id}")
    res = await runtime.capability.call(
        CapabilityCall(
            capability="work-item.comment",
            args={"work_item_ref": wi["work_item_ref"], "body": body},
            approval=ApprovalMetadata(risk=ApprovalRisk.UPDATE),
            idempotency=IdempotencyMetadata(
                key=str(payload.get("idempotency_key") or f"{tracking_id}:wi-comment")
            ),
        )
    )
    return {
        "gated": False,
        "phase": "comment_ticket",
        "tracking_id": tracking_id,
        "ok": bool(res.ok),
        "error": res.error,
        "skipped": False,
        "effect": "admin",
    }


@activity.defn(name="support_agent.incident.evaluate_recovery")
async def evaluate_recovery_activity(payload: dict[str, Any]) -> dict[str, Any]:
    tracking_id = str(payload.get("tracking_id") or "")
    if not incident_parity_enabled():
        return _gate_payload("evaluate_recovery", tracking_id)
    policy = select_policy(dict(payload.get("alert") or {}))
    if payload.get("policy"):
        from am_support_agent.contracts.incident import IncidentEvidencePolicy

        policy = IncidentEvidencePolicy.model_validate(payload["policy"])
    from am_support_agent.contracts.incident import EvidenceObservation

    batches: list[list] = []
    for batch in payload.get("sample_batches") or []:
        obs = [
            EvidenceObservation.model_validate(o)
            for o in batch
            if isinstance(o, dict)
        ]
        batches.append(obs)
    result = evaluate_recovery(sample_batches=batches, policy=policy)
    return {
        "gated": False,
        "phase": "evaluate_recovery",
        "tracking_id": tracking_id,
        **result,
    }


@activity.defn(name="support_agent.incident.close_ticket")
async def close_ticket(payload: dict[str, Any]) -> dict[str, Any]:
    tracking_id = str(payload.get("tracking_id") or "")
    if not incident_parity_enabled():
        return _gate_payload("close_ticket", tracking_id)
    wi = dict(payload.get("work_item") or {})
    if not wi.get("work_item_ref"):
        return {
            "gated": False,
            "phase": "close_ticket",
            "tracking_id": tracking_id,
            "skipped": True,
            "ok": False,
        }
    if not payload.get("recovered"):
        return {
            "gated": False,
            "phase": "close_ticket",
            "tracking_id": tracking_id,
            "ok": False,
            "error": "refusing close without recovered=true",
        }
    runtime = build_runtime()
    res = await runtime.capability.call(
        CapabilityCall(
            capability="work-item.transition",
            args={
                "work_item_ref": wi["work_item_ref"],
                "status": "closed",
                "reason": "recovered",
            },
            approval=ApprovalMetadata(risk=ApprovalRisk.UPDATE),
            idempotency=IdempotencyMetadata(key=f"{tracking_id}:wi-close"),
        )
    )
    work_item = dict(wi)
    if res.ok and isinstance(res.data, dict):
        work_item = _work_item_from_data(res.data, provider=res.provider).model_dump()
        work_item["status"] = work_item.get("status") or "closed"
    return {
        "gated": False,
        "phase": "close_ticket",
        "tracking_id": tracking_id,
        "ok": bool(res.ok),
        "error": res.error,
        "work_item": work_item,
        "effect": "admin",
    }


@activity.defn(name="support_agent.incident.notify_resolved")
async def notify_resolved(payload: dict[str, Any]) -> dict[str, Any]:
    tracking_id = str(payload.get("tracking_id") or "")
    if not incident_parity_enabled():
        return _gate_payload("notify_resolved", tracking_id)
    if not payload.get("recovered"):
        return {
            "gated": False,
            "phase": "notify_resolved",
            "tracking_id": tracking_id,
            "ok": False,
            "error": "refusing resolved notify without recovered=true",
        }
    runtime = build_runtime()
    owner = dict(payload.get("owner") or {})
    channel = str(owner.get("channel_ref") or "cliq:lab")
    res = await runtime.capability.call(
        CapabilityCall(
            capability="chat.message.send",
            args={
                "channel_ref": channel,
                "body": f"Incident recovered for {tracking_id}",
            },
            approval=ApprovalMetadata(risk=ApprovalRisk.SEND),
            idempotency=IdempotencyMetadata(key=f"{tracking_id}:notify-resolved"),
        )
    )
    return {
        "gated": False,
        "phase": "notify_resolved",
        "tracking_id": tracking_id,
        "ok": bool(res.ok),
        "error": res.error,
        "effect": "notify",
    }


@activity.defn(name="support_agent.incident.record_outcome_feedback")
async def record_outcome_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    tracking_id = str(payload.get("tracking_id") or "")
    episode_id = str(payload.get("episode_id") or "")
    outcome = str(payload.get("outcome") or "confirmed")
    evidence_items = _coerce_evidence_items(
        list(payload.get("evidence") or []), tracking_id=tracking_id
    )
    fb = ingest_feedback_event(
        {
            "episode_id": episode_id,
            "tracking_id": tracking_id,
            "kind": "outcome",
            "rating": outcome,
            "notes": str(payload.get("notes") or "terminal outcome"),
            "outcome": outcome,
            "idempotency_key": f"{tracking_id}:outcome:{episode_id}:{outcome}",
            "payload": {
                "evidence": evidence_items,
                "recovered": bool(payload.get("recovered")),
            },
        }
    )
    if episode_id:
        try:
            build_runtime().episodes.update_outcome(
                episode_id,
                outcome=outcome,
                verify_status="passed" if payload.get("recovered") else "failed",
                evidence=evidence_items,
            )
        except KeyError:
            pass
    return {
        "gated": False,
        "phase": "record_outcome_feedback",
        "tracking_id": tracking_id,
        "feedback": fb,
        "outcome": outcome,
    }


def _coerce_evidence_items(
    raw: list[Any], *, tracking_id: str
) -> list[dict[str, Any]]:
    """Map EvidenceObservation-like dicts to EvidenceItem {kind, ref, provenance}."""
    items: list[dict[str, Any]] = []
    for i, item in enumerate(raw or []):
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "observe")
        # Already EvidenceItem-shaped (has ref, no observation payload fields).
        if item.get("ref") and "healthy" not in item and "transport_ok" not in item:
            items.append(
                {
                    "kind": kind,
                    "ref": str(item["ref"]),
                    "provenance": str(item.get("provenance") or "observe"),
                }
            )
            continue
        ref = str(
            item.get("query_ref")
            or item.get("ref")
            or f"{tracking_id}:{kind}:{i}"
        )
        items.append({"kind": kind, "ref": ref, "provenance": "observe"})
    return items


@activity.defn(name="support_agent.incident.extract_remediation_candidate")
async def extract_remediation_candidate(payload: dict[str, Any]) -> dict[str, Any]:
    tracking_id = str(payload.get("tracking_id") or "")
    if not incident_parity_enabled():
        return _gate_payload("extract_remediation_candidate", tracking_id)
    actions = list(payload.get("actions") or [])
    steps = extract_remediation_steps(actions)
    if not steps:
        return {
            "gated": False,
            "phase": "extract_remediation_candidate",
            "tracking_id": tracking_id,
            "created": False,
            "reason": "no remediation-effect steps executed",
            "candidate": None,
        }
    alert = dict(payload.get("alert") or {})
    policy = dict(payload.get("policy") or {})
    candidate = upsert_candidate(
        RemediationCandidate(
            episode_id=str(payload.get("episode_id") or ""),
            tracking_id=tracking_id,
            service=str(alert.get("service") or ""),
            env=str(alert.get("env") or ""),
            fingerprint=str(alert.get("fingerprint") or ""),
            policy_id=str(policy.get("policy_id") or ""),
            policy_version=str(policy.get("policy_version") or ""),
            steps=steps,
            status="verified",
            preconditions={
                "decision": "active",
                "recovered": True,
            },
        )
    )
    return {
        "gated": False,
        "phase": "extract_remediation_candidate",
        "tracking_id": tracking_id,
        "created": True,
        "candidate": candidate.model_dump(),
    }


@activity.defn(name="support_agent.incident.evaluate_learning")
async def evaluate_learning(payload: dict[str, Any]) -> dict[str, Any]:
    tracking_id = str(payload.get("tracking_id") or "")
    episode_id = str(payload.get("episode_id") or "")
    if not episode_id:
        return {
            "gated": False,
            "phase": "evaluate_learning",
            "tracking_id": tracking_id,
            "ok": False,
            "error": "episode_id required",
        }
    result = evaluate_episode(episode_id)
    return {
        "gated": False,
        "phase": "evaluate_learning",
        "tracking_id": tracking_id,
        **result,
        "auto_promote": False,
    }


@activity.defn(name="support_agent.incident.parse_alert_feedback")
async def parse_alert_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    tracking_id = str(payload.get("tracking_id") or "")
    feedback = dict(payload.get("feedback") or {})
    kind = str(feedback.get("kind") or "").lower()
    text = str(feedback.get("notes") or feedback.get("text") or "").lower()
    alert = dict(payload.get("alert") or {})
    if kind == "silence" or "silence" in text:
        minutes = int(feedback.get("duration_minutes") or 60)
        minutes = max(5, min(minutes, 60 * 24 * 14))
        env = str(feedback.get("env") or alert.get("env") or "")
        service = str(feedback.get("service") or alert.get("service") or "")
        if not env or not service:
            return {
                "gated": False,
                "phase": "parse_alert_feedback",
                "tracking_id": tracking_id,
                "ok": False,
                "needs_hitl": True,
                "error": "silence requires env and service",
                "request": None,
            }
        request = {
            "kind": "silence",
            "tracking_id": tracking_id,
            "requester": str(feedback.get("requester") or ""),
            "reason": str(feedback.get("reason") or feedback.get("notes") or "user silence"),
            "duration_minutes": minutes,
            "env": env,
            "service": service,
            "matchers": {"env": env, "application": service},
            "request_id": str(feedback.get("request_id") or f"{tracking_id}:silence"),
        }
        return {
            "gated": False,
            "phase": "parse_alert_feedback",
            "tracking_id": tracking_id,
            "ok": True,
            "needs_approval": True,
            "request": request,
        }
    if kind in {"disable", "disable_candidate"} or "disable" in text:
        return {
            "gated": False,
            "phase": "parse_alert_feedback",
            "tracking_id": tracking_id,
            "ok": True,
            "needs_approval": False,
            "request": {
                "kind": "disable_candidate",
                "tracking_id": tracking_id,
                "reason": str(feedback.get("reason") or "permanent disable requested"),
                "requester": str(feedback.get("requester") or ""),
                "note": "permanent disable is a reviewed config change — not applied online",
            },
        }
    return {
        "gated": False,
        "phase": "parse_alert_feedback",
        "tracking_id": tracking_id,
        "ok": False,
        "needs_hitl": True,
        "error": "ambiguous feedback",
        "request": None,
    }


@activity.defn(name="support_agent.incident.apply_alert_silence")
async def apply_alert_silence(payload: dict[str, Any]) -> dict[str, Any]:
    tracking_id = str(payload.get("tracking_id") or "")
    if not incident_parity_enabled():
        return _gate_payload("apply_alert_silence", tracking_id)
    if not payload.get("approved"):
        return {
            "gated": False,
            "phase": "apply_alert_silence",
            "tracking_id": tracking_id,
            "ok": False,
            "error": "silence requires approve.silence",
        }
    request = dict(payload.get("request") or {})
    runtime = build_runtime()
    res = await runtime.capability.call(
        CapabilityCall(
            capability="alert.silence.create",
            args={
                "env": str(request.get("env") or ""),
                "service": str(request.get("service") or ""),
                "minutes": int(request.get("duration_minutes") or 60),
                "reason": str(request.get("reason") or ""),
                "created_by": str(request.get("requester") or "support-agent"),
            },
            approval=ApprovalMetadata(risk=ApprovalRisk.CREATE),
            idempotency=IdempotencyMetadata(
                key=str(request.get("request_id") or f"{tracking_id}:silence")
            ),
        )
    )
    silence = dict(res.data or {}) if res.ok else {}
    if res.ok and payload.get("work_item", {}).get("work_item_ref"):
        await runtime.capability.call(
            CapabilityCall(
                capability="work-item.comment",
                args={
                    "work_item_ref": payload["work_item"]["work_item_ref"],
                    "body": (
                        f"Silence applied id={silence.get('silence_id')} "
                        f"until {silence.get('ends_at')}"
                    ),
                },
                approval=ApprovalMetadata(risk=ApprovalRisk.UPDATE),
                idempotency=IdempotencyMetadata(key=f"{tracking_id}:silence-comment"),
            )
        )
    if res.ok:
        ingest_feedback_event(
            {
                "episode_id": str(payload.get("episode_id") or ""),
                "tracking_id": tracking_id,
                "kind": "silence",
                "rating": "applied",
                "notes": "approved temporary silence",
                "outcome": "silence_applied",
                "idempotency_key": str(request.get("request_id") or f"{tracking_id}:silence-fb"),
                "payload": silence,
            }
        )
    return {
        "gated": False,
        "phase": "apply_alert_silence",
        "tracking_id": tracking_id,
        "ok": bool(res.ok),
        "error": res.error,
        "silence": silence,
        "effect": "admin",
    }


@activity.defn(name="support_agent.incident.record_hitl")
async def record_hitl(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist HITL outcome metadata into episodic/feedback stores."""
    tracking_id = str(payload.get("tracking_id") or "")
    hitl = dict(payload.get("hitl") or {})
    episode_id = str(payload.get("episode_id") or "")
    outcome = "hitl_recorded"
    if hitl.get("investigation_approved") or hitl.get("approved"):
        outcome = "hitl_approved"
    elif hitl.get("known_fix_approved"):
        outcome = "known_fix_approved"
    elif hitl.get("silence_approved"):
        outcome = "silence_approved"
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
            "idempotency_key": f"{tracking_id}:hitl:{episode_id}:{outcome}",
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


@activity.defn(name="support_agent.incident.execute_actions")
async def execute_actions(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute planned/known-fix actions (remediation or admin)."""
    tracking_id = str(payload.get("tracking_id") or "")
    if not incident_parity_enabled():
        return _gate_payload("execute_actions", tracking_id)
    runtime = build_runtime()
    actions = list(payload.get("actions") or [])
    results: list[dict[str, Any]] = []
    for idx, action in enumerate(actions):
        capability = str(action.get("capability") or "")
        if not capability:
            continue
        effect = str(action.get("effect") or classify_effect(capability))
        risk = ApprovalRisk.SEND if effect == "notify" else ApprovalRisk.UPDATE
        if "create" in capability:
            risk = ApprovalRisk.CREATE
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
                "args": dict(action.get("args") or {}),
                "ok": res.ok,
                "error": res.error,
                "effect": effect,
                "version": str(action.get("version") or "1"),
                "risk": risk.value,
            }
        )
    return {
        "gated": False,
        "phase": "execute_actions",
        "tracking_id": tracking_id,
        "results": results,
        "actions": results,
    }


# ---------------------------------------------------------------------------
# Compatibility wrappers (tests / gradual cutover)
# ---------------------------------------------------------------------------


@activity.defn(name="support_agent.incident.bootstrap")
async def bootstrap_incident(payload: dict[str, Any]) -> dict[str, Any]:
    """Compatibility wrapper — sequential lifecycle through intelligence gate."""
    tracking_id = str(payload.get("tracking_id") or "")
    if not incident_parity_enabled():
        return _gate_payload("bootstrap", tracking_id)

    norm = await normalize_alert(payload)
    mem = await retrieve_memory(
        {
            "tracking_id": tracking_id,
            "alert": norm["alert"],
            "policy": norm.get("policy"),
        }
    )
    metrics = await query_metrics(
        {"tracking_id": tracking_id, "alert": norm["alert"]}
    )
    logs = await query_logs({"tracking_id": tracking_id, "alert": norm["alert"]})
    gate = await intelligence_gate(
        {
            "tracking_id": tracking_id,
            "alert": norm["alert"],
            "observations": [
                metrics.get("observation") or {},
                logs.get("observation") or {},
            ],
        }
    )
    if gate.get("stop"):
        ep = await persist_episode_activity(
            {
                "tracking_id": tracking_id,
                "run_ref": norm.get("run_ref"),
                "alert": norm["alert"],
                "observations": [
                    metrics.get("observation") or {},
                    logs.get("observation") or {},
                ],
                "observe": [
                    metrics.get("observe_evidence") or {},
                    logs.get("observe_evidence") or {},
                ],
                "validation": gate.get("validation"),
                "decision": (gate.get("decision") or {}).get("decision"),
                "similar_incident_ids": mem.get("similar_incident_ids"),
                "similar_summaries": mem.get("similar_summaries"),
                "catalog_refs": mem.get("catalog_refs"),
                "policy": gate.get("policy"),
                "outcome": "not_confirmed",
                "actions": [],
            }
        )
        return {
            "gated": False,
            "phase": "bootstrap",
            "tracking_id": tracking_id,
            "run_ref": norm.get("run_ref"),
            "validation": gate.get("validation"),
            "actions": [],
            "episode_id": ep.get("episode_id"),
            "similar_summaries": mem.get("similar_summaries"),
            "needs_hitl": False,
            "continue": False,
            "stop": True,
            "context": ep.get("context"),
        }

    # For compatibility with older tests that expected ticket create during bootstrap:
    # when continuing, create/assign ticket and plan notify actions.
    owner = await resolve_owner({"tracking_id": tracking_id, "alert": norm["alert"]})
    created = await create_ticket({"tracking_id": tracking_id, "alert": norm["alert"]})
    assigned = await assign_ticket(
        {
            "tracking_id": tracking_id,
            "work_item": created.get("work_item"),
            "owner": owner.get("owner"),
        }
    )
    from am_support_agent.contracts.incident import IncidentContext

    wi = None
    if assigned.get("work_item"):
        wi = WorkItemRef.model_validate(assigned["work_item"])
    own = None
    if owner.get("owner"):
        own = DirectoryOwner.model_validate(owner["owner"])
    observe = [
        ObserveEvidence.model_validate(metrics["observe_evidence"]),
        ObserveEvidence.model_validate(logs["observe_evidence"]),
    ]
    ctx = ContextBuilder().build(
        tracking_id=tracking_id,
        run_ref=str(norm.get("run_ref") or tracking_id),
        alert=norm["alert"],
        work_item=wi,
        owner=own,
        observe=observe,
        similar_incident_ids=list(mem.get("similar_incident_ids") or []),
        similar_summaries=list(mem.get("similar_summaries") or []),
        catalog_refs=list(mem.get("catalog_refs") or []),
    )
    # Ticket completeness can still force HITL in the compatibility path.
    needs_hitl = bool(gate.get("needs_hitl"))
    if wi is None or not wi.assignee_ref:
        needs_hitl = True
        validation = IncidentValidation(
            status=IncidentValidationStatus.INCONCLUSIVE,
            confidence=0.2,
            reasons=["work item missing or unassigned"],
            missing_evidence=["work_item" if wi is None else "assignee"],
            work_item_ok=False,
            policy_version=str((gate.get("policy") or {}).get("policy_version") or ""),
        )
        cont = False
    else:
        validation = IncidentValidation.model_validate(gate["validation"])
        cont = bool(gate.get("continue")) and not needs_hitl

    actions = ActionPlanner().plan(validation=validation, ctx=ctx) if cont else []
    ep = await persist_episode_activity(
        {
            "tracking_id": tracking_id,
            "run_ref": norm.get("run_ref"),
            "alert": norm["alert"],
            "owner": owner.get("owner"),
            "work_item": assigned.get("work_item"),
            "observations": [
                metrics.get("observation") or {},
                logs.get("observation") or {},
            ],
            "observe": [o.model_dump() for o in observe],
            "validation": validation.model_dump(),
            "decision": validation.status.value,
            "actions": actions,
            "similar_incident_ids": mem.get("similar_incident_ids"),
            "similar_summaries": mem.get("similar_summaries"),
            "catalog_refs": mem.get("catalog_refs"),
            "policy": gate.get("policy"),
            "known_fix": mem.get("known_fix"),
            "outcome": "pending",
        }
    )
    return {
        "gated": False,
        "phase": "bootstrap",
        "tracking_id": tracking_id,
        "run_ref": norm.get("run_ref"),
        "context": ep.get("context") or ctx.model_dump(),
        "validation": validation.model_dump(),
        "actions": actions,
        "episode_id": ep.get("episode_id"),
        "similar_summaries": mem.get("similar_summaries"),
        "needs_hitl": needs_hitl,
        "continue": cont,
        "stop": False,
        "known_fix": mem.get("known_fix"),
        "steps": {
            "normalize": norm,
            "memory": mem,
            "metrics": metrics,
            "logs": logs,
            "gate": gate,
            "owner": owner,
            "create": created,
            "assign": assigned,
        },
    }


@activity.defn(name="support_agent.incident.finalize")
async def finalize_incident(payload: dict[str, Any]) -> dict[str, Any]:
    """Compatibility: dispatch planned notify/comment actions."""
    tracking_id = str(payload.get("tracking_id") or "")
    if not incident_parity_enabled():
        return _gate_payload("finalize", tracking_id)
    executed = await execute_actions(payload)
    results = list(executed.get("results") or [])
    outcome = (
        "confirmed"
        if all(r.get("ok") for r in results) or not results
        else "finalize_partial"
    )
    episode_id = str(payload.get("episode_id") or "")
    if episode_id:
        try:
            build_runtime().episodes.update_outcome(
                episode_id,
                outcome=outcome,
                verify_status="passed" if outcome == "confirmed" else "partial",
                evidence=[
                    {
                        "kind": "finalize",
                        "ref": r["capability"],
                        "provenance": "capability",
                    }
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


INCIDENT_ACTIVITIES = [
    check_parity,
    normalize_alert,
    retrieve_memory,
    query_metrics,
    query_logs,
    verify_metrics,
    verify_logs,
    intelligence_gate,
    propose_known_fix,
    plan_investigation,
    resolve_owner,
    create_ticket,
    assign_ticket,
    persist_episode_activity,
    notify_firing,
    comment_ticket,
    evaluate_recovery_activity,
    close_ticket,
    notify_resolved,
    record_outcome_feedback,
    extract_remediation_candidate,
    evaluate_learning,
    parse_alert_feedback,
    apply_alert_silence,
    record_hitl,
    execute_actions,
    bootstrap_incident,
    finalize_incident,
]
