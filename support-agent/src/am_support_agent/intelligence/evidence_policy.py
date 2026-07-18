"""Versioned evidence / recovery policies — deterministic, fail-closed."""

from __future__ import annotations

from typing import Any

from am_support_agent.contracts.enums import IncidentValidationStatus
from am_support_agent.contracts.incident import (
    EvidenceObservation,
    EvidencePredicateResult,
    IncidentEvidencePolicy,
    PolicyQuerySpec,
)


DEFAULT_POLICY = IncidentEvidencePolicy(
    policy_id="default-firing-v1",
    policy_version="1",
    match_alertnames=[],
    match_fingerprints=[],
    environments=[],
    require_metrics=True,
    require_logs=False,
    metric_queries=[
        PolicyQuerySpec(
            kind="metrics",
            query_ref="service_health",
            lookback_seconds=300,
            freshness_seconds=180,
        )
    ],
    log_queries=[],
    min_samples=1,
    recovery_stability_samples=2,
    recovery_stability_seconds=60,
    healthy_when_firing=False,
)


def select_policy(alert: dict[str, Any]) -> IncidentEvidencePolicy:
    """Select a policy by alertname/fingerprint/env; default is fail-closed."""
    # Explicit policies can be added later; default covers all alerts.
    _ = alert
    return DEFAULT_POLICY.model_copy(deep=True)


def _points(data: dict[str, Any]) -> list[Any]:
    for key in ("points", "values", "samples", "series"):
        raw = data.get(key)
        if isinstance(raw, list):
            return raw
    return []


def _numeric_values(data: dict[str, Any]) -> list[float]:
    out: list[float] = []
    for item in _points(data):
        if isinstance(item, (int, float)):
            out.append(float(item))
        elif isinstance(item, dict):
            for key in ("value", "v", "y"):
                if isinstance(item.get(key), (int, float)):
                    out.append(float(item[key]))
                    break
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            try:
                out.append(float(item[-1]))
            except (TypeError, ValueError):
                continue
    if not out and isinstance(data.get("value"), (int, float)):
        out.append(float(data["value"]))
    return out


def evaluate_observation(
    *,
    policy: IncidentEvidencePolicy,
    kind: str,
    transport_ok: bool,
    data: dict[str, Any],
    observed_at: str,
) -> EvidenceObservation:
    """Transport success alone is never service-health evidence."""
    predicates: list[EvidencePredicateResult] = []
    if not transport_ok:
        predicates.append(
            EvidencePredicateResult(
                name="transport_ok",
                passed=False,
                detail="capability/transport call failed",
            )
        )
        return EvidenceObservation(
            kind=kind,
            transport_ok=False,
            parseable=False,
            healthy=False,
            observed_at=observed_at,
            summary=f"{kind}: transport error",
            data=data,
            predicates=predicates,
        )

    parseable = True
    healthy: bool | None = None
    if kind == "metrics":
        values = _numeric_values(data)
        status_hint = str(data.get("status") or data.get("health") or "").lower()
        summary = str(data.get("summary") or "")
        if values:
            # Convention: value > 0 while firing means still unhealthy unless
            # the payload explicitly marks health.
            if status_hint in {"ok", "healthy", "resolved"}:
                healthy = True
            elif status_hint in {"firing", "unhealthy", "error", "critical"}:
                healthy = False
            else:
                healthy = all(v <= 0 for v in values)
            predicates.append(
                EvidencePredicateResult(
                    name="metric_threshold",
                    passed=bool(healthy),
                    detail=f"values={values[:5]} status_hint={status_hint or 'none'}",
                )
            )
        elif status_hint in {"ok", "healthy", "resolved"} or "healthy" in summary.lower():
            healthy = True
            predicates.append(
                EvidencePredicateResult(
                    name="status_hint",
                    passed=True,
                    detail=status_hint or summary[:80],
                )
            )
        elif status_hint in {"firing", "unhealthy", "error", "critical"} or "error" in summary.lower():
            healthy = False
            predicates.append(
                EvidencePredicateResult(
                    name="status_hint",
                    passed=False,
                    detail=status_hint or summary[:80],
                )
            )
        else:
            # Fake/memory providers often return empty points — treat as
            # parseable but unknown health (inconclusive, not recovered).
            parseable = True
            healthy = None
            predicates.append(
                EvidencePredicateResult(
                    name="metric_values_present",
                    passed=False,
                    detail="no numeric samples or explicit health status",
                )
            )
    elif kind == "logs":
        if not policy.require_logs:
            return EvidenceObservation(
                kind=kind,
                transport_ok=True,
                parseable=True,
                healthy=True,
                observed_at=observed_at,
                summary="logs not required by policy",
                data=data,
                predicates=[
                    EvidencePredicateResult(
                        name="logs_optional",
                        passed=True,
                        detail="policy.require_logs=false",
                    )
                ],
            )
        error_count = data.get("error_count")
        if isinstance(error_count, (int, float)):
            healthy = float(error_count) <= 0
            predicates.append(
                EvidencePredicateResult(
                    name="log_error_count",
                    passed=bool(healthy),
                    detail=f"error_count={error_count}",
                )
            )
        else:
            healthy = None
            predicates.append(
                EvidencePredicateResult(
                    name="log_error_count",
                    passed=False,
                    detail="error_count missing",
                )
            )
    else:
        healthy = None
        predicates.append(
            EvidencePredicateResult(
                name="unsupported_kind",
                passed=False,
                detail=kind,
            )
        )

    return EvidenceObservation(
        kind=kind,
        transport_ok=True,
        parseable=parseable,
        healthy=healthy,
        observed_at=observed_at,
        summary=str(data.get("summary") or f"{kind} observation"),
        data=data,
        predicates=predicates,
        query_ref=str(data.get("query_ref") or ""),
    )


def classify_from_evidence(
    *,
    alert: dict[str, Any],
    observations: list[EvidenceObservation],
    policy: IncidentEvidencePolicy,
) -> dict[str, Any]:
    """Initial intelligence gate — before ticketing side effects."""
    status_hint = str(alert.get("status") or alert.get("state") or "").lower()
    reasons: list[str] = []
    missing: list[str] = []

    if status_hint in {"resolved", "false_positive", "not_firing", "ok"}:
        return {
            "status": IncidentValidationStatus.NOT_CONFIRMED.value,
            "decision": "already_healthy",
            "confidence": 0.85,
            "reasons": [f"alert status indicates {status_hint}"],
            "missing_evidence": [],
            "policy_id": policy.policy_id,
            "policy_version": policy.policy_version,
            "needs_hitl": False,
            "continue": False,
            "stop": True,
        }

    metrics = [o for o in observations if o.kind == "metrics"]
    logs = [o for o in observations if o.kind == "logs"]

    if policy.require_metrics:
        if not metrics:
            missing.append("metrics")
            reasons.append("no metrics observation")
        elif any(not o.transport_ok for o in metrics):
            missing.append("metrics_transport")
            reasons.append("metrics transport failed")
        elif all(o.healthy is None for o in metrics):
            missing.append("metrics_health")
            reasons.append("metrics returned no parseable health signal")

    if policy.require_logs:
        if not logs:
            missing.append("logs")
            reasons.append("no logs observation")
        elif any(not o.transport_ok for o in logs):
            missing.append("logs_transport")
            reasons.append("logs transport failed")
        elif all(o.healthy is None for o in logs):
            missing.append("logs_health")
            reasons.append("logs returned no parseable health signal")

    if missing:
        return {
            "status": IncidentValidationStatus.INCONCLUSIVE.value,
            "decision": "inconclusive",
            "confidence": 0.2,
            "reasons": reasons,
            "missing_evidence": missing,
            "policy_id": policy.policy_id,
            "policy_version": policy.policy_version,
            "needs_hitl": True,
            "continue": False,
            "stop": False,
        }

    # Firing + evidence present → active investigation (even if samples look healthy;
    # Grafana still says firing, so we investigate).
    unhealthy = [o for o in observations if o.healthy is False]
    return {
        "status": IncidentValidationStatus.CONFIRMED.value,
        "decision": "active",
        "confidence": 0.75 if unhealthy else 0.65,
        "reasons": (
            ["firing alert with unhealthy evidence"]
            if unhealthy
            else ["firing alert with parseable evidence — investigate"]
        ),
        "missing_evidence": [],
        "policy_id": policy.policy_id,
        "policy_version": policy.policy_version,
        "needs_hitl": False,
        "continue": True,
        "stop": False,
    }


def evaluate_recovery(
    *,
    sample_batches: list[list[EvidenceObservation]],
    policy: IncidentEvidencePolicy,
) -> dict[str, Any]:
    """Require multiple stable healthy observation batches after alert.resolved."""
    required = max(1, int(policy.recovery_stability_samples))
    if len(sample_batches) < required:
        return {
            "recovered": False,
            "status": "insufficient_samples",
            "reasons": [f"need {required} observation batches, have {len(sample_batches)}"],
            "policy_id": policy.policy_id,
            "policy_version": policy.policy_version,
        }

    reasons: list[str] = []
    for idx, batch in enumerate(sample_batches[-required:]):
        metrics = [o for o in batch if o.kind == "metrics"]
        logs = [o for o in batch if o.kind == "logs"]
        if policy.require_metrics:
            if not metrics or any(not o.transport_ok for o in metrics):
                reasons.append(f"batch[{idx}]: metrics missing/failed")
                continue
            if any(o.healthy is not True for o in metrics):
                reasons.append(f"batch[{idx}]: metrics not explicitly healthy")
                continue
        if policy.require_logs:
            if not logs or any(not o.transport_ok for o in logs):
                reasons.append(f"batch[{idx}]: logs missing/failed")
                continue
            if any(o.healthy is not True for o in logs):
                reasons.append(f"batch[{idx}]: logs not explicitly healthy")
                continue
        # If logs optional and metrics healthy → batch ok
        if policy.require_metrics and all(o.healthy is True for o in metrics):
            continue
        if not policy.require_metrics and not policy.require_logs:
            reasons.append(f"batch[{idx}]: policy requires no evidence")
    if reasons:
        return {
            "recovered": False,
            "status": "unhealthy_or_inconclusive",
            "reasons": reasons,
            "policy_id": policy.policy_id,
            "policy_version": policy.policy_version,
        }
    return {
        "recovered": True,
        "status": "recovered",
        "reasons": [f"{required} consecutive healthy observation batches"],
        "policy_id": policy.policy_id,
        "policy_version": policy.policy_version,
    }


__all__ = [
    "DEFAULT_POLICY",
    "select_policy",
    "evaluate_observation",
    "classify_from_evidence",
    "evaluate_recovery",
]
