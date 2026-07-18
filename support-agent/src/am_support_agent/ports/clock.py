from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Protocol


class Clock(Protocol):
    def now_iso(self) -> str: ...


class IdGenerator(Protocol):
    def new_id(self, prefix: str = "") -> str: ...


class SystemClock:
    def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()


class UuidGenerator:
    def new_id(self, prefix: str = "") -> str:
        value = uuid.uuid4().hex
        return f"{prefix}{value}" if prefix else value
