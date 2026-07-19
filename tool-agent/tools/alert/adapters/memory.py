from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


class MemoryAdapter:
    silences: list[dict[str, Any]] = []

    @property
    def available(self) -> bool:
        return True

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        _ = read_only
        if operation == "silence.create":
            env = str(params.get("env") or "").strip()
            service = str(params.get("service") or "").strip()
            minutes = int(params.get("minutes") or 60)
            if not env or not service:
                raise ValueError("env and service are required (refusing global silence)")
            if minutes < 5 or minutes > 60 * 24 * 14:
                raise ValueError("duration must be between 5 minutes and 14 days")
            starts = datetime.now(timezone.utc)
            ends = starts + timedelta(minutes=minutes)
            silence_id = f"mem:silence:{len(self.silences) + 1}"
            row = {
                "silence_id": silence_id,
                "starts_at": starts.isoformat().replace("+00:00", "Z"),
                "ends_at": ends.isoformat().replace("+00:00", "Z"),
                "env": env,
                "service": service,
                "minutes": minutes,
                "reason": params.get("reason") or "",
                "created_by": params.get("created_by") or "tool-agent",
            }
            self.silences.append(row)
            return dict(row)
        if operation == "silence.get":
            sid = str(params.get("silence_id") or "")
            for row in self.silences:
                if row.get("silence_id") == sid:
                    return dict(row)
            return {"silence_id": sid, "found": False}
        if operation == "silence.expire":
            sid = str(params.get("silence_id") or "")
            self.silences = [r for r in self.silences if r.get("silence_id") != sid]
            return {"silence_id": sid, "expired": True}
        raise ValueError(f"unknown operation {operation!r}")
