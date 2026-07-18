from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class IdempotencyRecord:
    key: str
    plan_hash: str
    result: dict[str, Any]
    expires_at: float


class IdempotencyStore:
    def __init__(self, *, ttl_seconds: float = 3600.0) -> None:
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._items: dict[str, IdempotencyRecord] = {}

    def _purge(self) -> None:
        now = time.time()
        expired = [k for k, v in self._items.items() if v.expires_at <= now]
        for key in expired:
            self._items.pop(key, None)

    def get(self, key: str, *, plan_hash: str | None = None) -> dict[str, Any] | None:
        with self._lock:
            self._purge()
            rec = self._items.get(key)
            if not rec:
                return None
            if plan_hash is not None and rec.plan_hash != plan_hash:
                return None
            return dict(rec.result)

    def put(self, key: str, *, plan_hash: str, result: dict[str, Any]) -> None:
        with self._lock:
            self._purge()
            self._items[key] = IdempotencyRecord(
                key=key,
                plan_hash=plan_hash,
                result=dict(result),
                expires_at=time.time() + self._ttl,
            )

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


_STORE = IdempotencyStore()


def get_idempotency_store() -> IdempotencyStore:
    return _STORE
