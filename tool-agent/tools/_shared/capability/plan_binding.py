from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass

from app.models.intent import IntentDocument

_TTL_SECONDS = 300
_store: dict[str, PlanBinding] = {}


@dataclass
class PlanBinding:
    plan_hash: str
    phrase: str
    backend: str
    operation: str
    expires_at: float


def intent_plan_hash(intent: IntentDocument) -> str:
    payload = intent.model_dump(mode="json")
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def _purge() -> None:
    now = time.time()
    for token in [t for t, e in _store.items() if e.expires_at <= now]:
        _store.pop(token, None)


def issue_plan_binding(intent: IntentDocument) -> tuple[str, str, str]:
    """Return (plan_hash, confirmation_token, confirmation_phrase)."""
    _purge()
    plan_hash = intent_plan_hash(intent)
    token = secrets.token_urlsafe(24)
    suffix = secrets.token_hex(3).upper()
    phrase = f"CONFIRM {intent.backend.upper()} WRITE {suffix}"
    _store[token] = PlanBinding(
        plan_hash=plan_hash,
        phrase=phrase,
        backend=intent.backend,
        operation=intent.operation,
        expires_at=time.time() + _TTL_SECONDS,
    )
    return plan_hash, token, phrase


def verify_plan_binding(
    *,
    token: str,
    phrase: str,
    intent: IntentDocument,
    plan_hash: str | None = None,
) -> bool:
    _purge()
    entry = _store.get(token)
    if not entry:
        return False
    if entry.expires_at <= time.time():
        _store.pop(token, None)
        return False
    if entry.phrase != phrase:
        return False
    expected = intent_plan_hash(intent)
    if entry.plan_hash != expected:
        return False
    if plan_hash is not None and plan_hash != expected:
        return False
    if entry.backend != intent.backend or entry.operation != intent.operation:
        return False
    _store.pop(token, None)
    return True


def clear_plan_bindings() -> None:
    _store.clear()
