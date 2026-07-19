"""In-memory remediation candidate store (Postgres table reuse later)."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from am_support_agent.contracts.incident import RemediationCandidate, RemediationStep
from am_support_agent.ports.clock import SystemClock, UuidGenerator

_clock = SystemClock()
_ids = UuidGenerator()
_MEMORY: dict[str, RemediationCandidate] = {}


ADMIN_CAPABILITIES = frozenset(
    {
        "work-item.create",
        "work-item.assign",
        "work-item.get",
        "work-item.comment",
        "work-item.transition",
        "directory.owner.resolve",
        "chat.message.send",
        "chat.card.send",
        "mail.message.send",
    }
)
OBSERVE_PREFIXES = ("observe.",)
NOTIFY_PREFIXES = ("chat.", "mail.")


def classify_effect(capability: str) -> str:
    cap = (capability or "").strip()
    if cap in ADMIN_CAPABILITIES or cap.startswith("work-item."):
        if cap.startswith("chat.") or cap.startswith("mail."):
            return "notify"
        return "admin"
    if any(cap.startswith(p) for p in OBSERVE_PREFIXES):
        return "observe"
    if any(cap.startswith(p) for p in NOTIFY_PREFIXES):
        return "notify"
    if cap.startswith("alert.silence"):
        return "admin"
    # Unknown write/execute capabilities are treated as remediation candidates.
    return "remediation"


def step_hash_for(steps: list[RemediationStep]) -> str:
    raw = json.dumps(
        [s.model_dump(mode="json") for s in steps],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def extract_remediation_steps(actions: list[dict[str, Any]]) -> list[RemediationStep]:
    steps: list[RemediationStep] = []
    for action in actions:
        capability = str(action.get("capability") or "")
        if not capability:
            continue
        effect = str(action.get("effect") or classify_effect(capability))
        if effect != "remediation":
            continue
        if not bool(action.get("ok", True)):
            continue
        args = dict(action.get("args") or {})
        # Drop volatile fields from reusable schema.
        for key in ("idempotency_key", "work_item_ref", "timestamp", "tracking_id"):
            args.pop(key, None)
        steps.append(
            RemediationStep(
                capability=capability,
                args_schema=args,
                effect="remediation",
                risk=str(action.get("risk") or "update"),
                version=str(action.get("version") or "1"),
            )
        )
    return steps


def upsert_candidate(candidate: RemediationCandidate) -> RemediationCandidate:
    body = candidate
    if not body.candidate_id:
        body = body.model_copy(update={"candidate_id": _ids.new_id("rcand-")})
    if not body.created_at:
        body = body.model_copy(update={"created_at": _clock.now_iso()})
    if not body.step_hash and body.steps:
        body = body.model_copy(update={"step_hash": step_hash_for(body.steps)})
    _MEMORY[body.candidate_id] = body
    # Index latest by fingerprint scope
    key = _scope_key(body.service, body.env, body.fingerprint, body.policy_id)
    _MEMORY[f"scope:{key}"] = body
    return body


def _scope_key(service: str, env: str, fingerprint: str, policy_id: str) -> str:
    return "|".join(
        [
            (service or "").strip().lower(),
            (env or "").strip().lower(),
            (fingerprint or "").strip().lower(),
            (policy_id or "").strip().lower(),
        ]
    )


def find_matching_candidate(
    *,
    service: str,
    env: str,
    fingerprint: str,
    policy_id: str,
) -> RemediationCandidate | None:
    key = _scope_key(service, env, fingerprint, policy_id)
    hit = _MEMORY.get(f"scope:{key}")
    if hit is None or hit.status not in {"proposed", "approved", "verified"}:
        return None
    if not hit.steps:
        return None
    return hit


def clear_memory_store() -> None:
    _MEMORY.clear()


def remediation_store_enabled() -> bool:
    return os.getenv("SUPPORT_AGENT_REMEDIATION_MEMORY", "true").lower() in {
        "1",
        "true",
        "yes",
    }


__all__ = [
    "classify_effect",
    "step_hash_for",
    "extract_remediation_steps",
    "upsert_candidate",
    "find_matching_candidate",
    "clear_memory_store",
    "remediation_store_enabled",
]
