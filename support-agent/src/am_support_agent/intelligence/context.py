"""Context intelligence — build, validate, plan, evaluate (support-agent owned)."""

from __future__ import annotations

from typing import Any

from am_support_agent.contracts.capabilities import (
    DirectoryOwner,
    ObserveEvidence,
    WorkItemRef,
)
from am_support_agent.contracts.enums import IncidentValidationStatus
from am_support_agent.contracts.incident import IncidentContext, IncidentValidation
from am_support_agent.contracts.schemas import EvidenceItem
from am_support_agent.ports.clock import Clock, SystemClock
from am_support_agent.stores.episodes import MemoryEpisodeStore


class ContextBuilder:
    def __init__(self, *, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()

    def build(
        self,
        *,
        tracking_id: str,
        run_ref: str,
        alert: dict[str, Any],
        work_item: WorkItemRef | None,
        owner: DirectoryOwner | None,
        observe: list[ObserveEvidence],
        similar_incident_ids: list[str],
        catalog_refs: list[str],
    ) -> IncidentContext:
        return IncidentContext(
            tracking_id=tracking_id,
            run_ref=run_ref,
            alert=dict(alert),
            work_item=work_item,
            owner=owner,
            observe=observe,
            similar_incidents=similar_incident_ids,
            memory_refs=list(similar_incident_ids),
            catalog_refs=catalog_refs,
            built_at=self._clock.now_iso(),
        )


class IncidentValidator:
    """Deterministic fail-closed gate before LLM judgment."""

    POLICY_VERSION = "incident-validate-v1"

    def validate(self, ctx: IncidentContext) -> IncidentValidation:
        reasons: list[str] = []
        missing: list[str] = []
        evidence: list[EvidenceItem] = []
        work_item_ok = False

        wi = ctx.work_item
        if wi is None or not wi.work_item_ref:
            missing.append("work_item")
            reasons.append("work item missing after create/assign")
        else:
            work_item_ok = True
            evidence.append(
                EvidenceItem(
                    kind="work_item",
                    ref=wi.work_item_ref,
                    provenance=wi.provider or "work-item",
                )
            )
            if not wi.assignee_ref:
                missing.append("assignee")
                reasons.append("work item not assigned on read-back")
                work_item_ok = False

        fresh_observe = [o for o in ctx.observe if o.status == "ok"]
        if not fresh_observe:
            missing.append("observe")
            reasons.append("no fresh observe evidence")
        else:
            for obs in fresh_observe[:5]:
                evidence.append(
                    EvidenceItem(
                        kind=f"observe.{obs.kind}",
                        ref=obs.ref or obs.query_ref or obs.kind,
                        provenance="observe",
                    )
                )

        # Fail-closed: missing required evidence → inconclusive (never auto-confirm)
        if missing:
            return IncidentValidation(
                status=IncidentValidationStatus.INCONCLUSIVE,
                confidence=0.2,
                reasons=reasons or ["missing required evidence"],
                missing_evidence=missing,
                evidence=evidence,
                freshness_at=ctx.built_at,
                work_item_ok=work_item_ok,
                policy_version=self.POLICY_VERSION,
            )

        # Explicit not_confirmed only when alert marks resolved/false-positive
        alert = ctx.alert or {}
        status_hint = str(alert.get("status") or alert.get("state") or "").lower()
        if status_hint in {"resolved", "false_positive", "not_firing", "ok"}:
            return IncidentValidation(
                status=IncidentValidationStatus.NOT_CONFIRMED,
                confidence=0.85,
                reasons=[f"alert status indicates {status_hint}"],
                missing_evidence=[],
                evidence=evidence,
                freshness_at=ctx.built_at,
                work_item_ok=work_item_ok,
                policy_version=self.POLICY_VERSION,
            )

        return IncidentValidation(
            status=IncidentValidationStatus.CONFIRMED,
            confidence=0.75,
            reasons=["work item assigned and observe evidence present"],
            missing_evidence=[],
            evidence=evidence,
            freshness_at=ctx.built_at,
            work_item_ok=work_item_ok,
            policy_version=self.POLICY_VERSION,
        )


class ActionPlanner:
    """Propose only generic capability IDs after confirmation."""

    def plan(self, *, validation: IncidentValidation, ctx: IncidentContext) -> list[dict[str, Any]]:
        if validation.status != IncidentValidationStatus.CONFIRMED:
            return []
        actions: list[dict[str, Any]] = []
        channel = (ctx.owner.channel_ref if ctx.owner else None) or "cliq:lab"
        actions.append(
            {
                "capability": "chat.message.send",
                "args": {
                    "channel_ref": channel,
                    "body": f"Investigation started for {ctx.tracking_id}",
                },
            }
        )
        if ctx.work_item:
            actions.append(
                {
                    "capability": "work-item.comment",
                    "args": {
                        "work_item_ref": ctx.work_item.work_item_ref,
                        "body": f"Incident validated ({validation.status.value})",
                    },
                }
            )
        return actions


class OutcomeEvaluator:
    def evaluate(self, *, expected: str, observed: str) -> dict[str, Any]:
        ok = expected.strip().lower() == observed.strip().lower()
        return {
            "matched": ok,
            "expected": expected,
            "observed": observed,
            "outcome": "recovered" if ok else "unresolved",
        }


class EpisodeRetriever:
    def __init__(self, store: MemoryEpisodeStore) -> None:
        self._store = store

    def similar(self, alert: dict[str, Any], *, limit: int = 5) -> list[str]:
        from am_support_agent.contracts.incident import MemoryQuery

        q = MemoryQuery(
            service=str(alert.get("service") or ""),
            env=str(alert.get("env") or alert.get("environment") or ""),
            fingerprint=str(alert.get("fingerprint") or ""),
            limit=limit,
        )
        return [ep.episode_id for ep in self._store.query(q)]
