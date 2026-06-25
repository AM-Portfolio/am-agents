from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass

from app.models.intent import IntentDocument

_TTL_SECONDS = 300
_store: dict[str, "PendingVaultWrite"] = {}


@dataclass
class PendingVaultWrite:
    intent_hash: str
    phrase: str
    expires_at: float


def _intent_hash(intent: IntentDocument) -> str:
    payload = intent.model_dump(mode="json")
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def _purge_expired() -> None:
    now = time.time()
    expired = [token for token, entry in _store.items() if entry.expires_at <= now]
    for token in expired:
        _store.pop(token, None)


def issue_write_confirmation(intent: IntentDocument) -> tuple[str, str]:
    _purge_expired()
    token = secrets.token_urlsafe(24)
    suffix = secrets.token_hex(3).upper()
    phrase = f"CONFIRM VAULT WRITE {suffix}"
    _store[token] = PendingVaultWrite(
        intent_hash=_intent_hash(intent),
        phrase=phrase,
        expires_at=time.time() + _TTL_SECONDS,
    )
    return token, phrase


def verify_write_confirmation(token: str, phrase: str, intent: IntentDocument) -> bool:
    _purge_expired()
    entry = _store.get(token)
    if not entry:
        return False
    if entry.expires_at <= time.time():
        _store.pop(token, None)
        return False
    if entry.phrase != phrase:
        return False
    if entry.intent_hash != _intent_hash(intent):
        return False
    _store.pop(token, None)
    return True


def clear_store() -> None:
    _store.clear()
