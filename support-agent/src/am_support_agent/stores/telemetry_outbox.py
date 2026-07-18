"""Transactional outbox for agent-work events (memory + postgres)."""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Protocol

from am_support_agent.observability.agent_work import AgentWorkEvent


@dataclass
class OutboxRecord:
    event_id: str
    dedupe_key: str
    event_name: str
    event: dict[str, Any]
    delivered: bool = False
    attempts: int = 0
    last_error: str = ""


class TelemetryOutbox(Protocol):
    def append(self, event: AgentWorkEvent) -> OutboxRecord: ...

    def claim_batch(self, *, limit: int = 50, locker: str = "dispatcher") -> list[OutboxRecord]: ...

    def mark_delivered(self, event_id: str) -> None: ...

    def mark_failed(self, event_id: str, error: str) -> None: ...

    def pending_count(self) -> int: ...

    def ready(self) -> bool: ...


class MemoryTelemetryOutbox:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_dedupe: dict[str, OutboxRecord] = {}
        self._by_id: dict[str, OutboxRecord] = {}

    def append(self, event: AgentWorkEvent) -> OutboxRecord:
        with self._lock:
            existing = self._by_dedupe.get(event.dedupe_key)
            if existing:
                return existing
            rec = OutboxRecord(
                event_id=event.event_id,
                dedupe_key=event.dedupe_key,
                event_name=event.event_name,
                event=event.to_dict(),
            )
            self._by_dedupe[event.dedupe_key] = rec
            self._by_id[event.event_id] = rec
            return rec

    def claim_batch(self, *, limit: int = 50, locker: str = "dispatcher") -> list[OutboxRecord]:
        del locker
        with self._lock:
            pending = [r for r in self._by_id.values() if not r.delivered]
            return pending[:limit]

    def mark_delivered(self, event_id: str) -> None:
        with self._lock:
            rec = self._by_id.get(event_id)
            if rec:
                rec.delivered = True
                rec.last_error = ""

    def mark_failed(self, event_id: str, error: str) -> None:
        with self._lock:
            rec = self._by_id.get(event_id)
            if rec:
                rec.attempts += 1
                rec.last_error = (error or "")[:400]

    def pending_count(self) -> int:
        with self._lock:
            return sum(1 for r in self._by_id.values() if not r.delivered)

    def ready(self) -> bool:
        return True


class PostgresTelemetryOutbox:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(self._dsn, row_factory=dict_row)

    def append(self, event: AgentWorkEvent) -> OutboxRecord:
        payload = event.to_dict()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO support_agent.agent_work_event_outbox (
                        event_id, dedupe_key, event_name, workflow_id, workflow_run_id,
                        run_ref, tracking_id, status, phase, event_json, occurred_at
                    ) VALUES (
                        %(event_id)s, %(dedupe_key)s, %(event_name)s, %(workflow_id)s,
                        %(workflow_run_id)s, %(run_ref)s, %(tracking_id)s, %(status)s,
                        %(phase)s, %(event_json)s::jsonb, %(occurred_at)s::timestamptz
                    )
                    ON CONFLICT (dedupe_key) DO UPDATE
                      SET event_id = support_agent.agent_work_event_outbox.event_id
                    RETURNING event_id, dedupe_key, event_name, event_json,
                              delivered_at, attempts, last_error
                    """,
                    {
                        "event_id": event.event_id,
                        "dedupe_key": event.dedupe_key,
                        "event_name": event.event_name,
                        "workflow_id": event.workflow_id,
                        "workflow_run_id": event.workflow_run_id,
                        "run_ref": event.run_ref,
                        "tracking_id": event.tracking_id,
                        "status": event.status,
                        "phase": event.phase,
                        "event_json": json.dumps(payload),
                        "occurred_at": event.occurred_at,
                    },
                )
                row = cur.fetchone()
            conn.commit()
        return OutboxRecord(
            event_id=str(row["event_id"]),
            dedupe_key=str(row["dedupe_key"]),
            event_name=str(row["event_name"]),
            event=row["event_json"] if isinstance(row["event_json"], dict) else payload,
            delivered=row.get("delivered_at") is not None,
            attempts=int(row.get("attempts") or 0),
            last_error=str(row.get("last_error") or ""),
        )

    def claim_batch(self, *, limit: int = 50, locker: str = "dispatcher") -> list[OutboxRecord]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    WITH cte AS (
                      SELECT event_id FROM support_agent.agent_work_event_outbox
                      WHERE delivered_at IS NULL
                        AND available_at <= now()
                        AND (locked_until IS NULL OR locked_until < now())
                        AND attempts < 25
                      ORDER BY occurred_at
                      FOR UPDATE SKIP LOCKED
                      LIMIT %s
                    )
                    UPDATE support_agent.agent_work_event_outbox o
                    SET locked_by = %s,
                        locked_until = now() + interval '2 minutes',
                        attempts = o.attempts + 1
                    FROM cte WHERE o.event_id = cte.event_id
                    RETURNING o.event_id, o.dedupe_key, o.event_name, o.event_json,
                              o.attempts, o.last_error
                    """,
                    (limit, locker),
                )
                rows = cur.fetchall()
            conn.commit()
        out: list[OutboxRecord] = []
        for row in rows:
            body = row["event_json"]
            if not isinstance(body, dict):
                body = json.loads(body)
            out.append(
                OutboxRecord(
                    event_id=str(row["event_id"]),
                    dedupe_key=str(row["dedupe_key"]),
                    event_name=str(row["event_name"]),
                    event=body,
                    attempts=int(row["attempts"] or 0),
                    last_error=str(row.get("last_error") or ""),
                )
            )
        return out

    def mark_delivered(self, event_id: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE support_agent.agent_work_event_outbox
                    SET delivered_at = now(), locked_by = NULL, locked_until = NULL,
                        last_error = ''
                    WHERE event_id = %s
                    """,
                    (event_id,),
                )
            conn.commit()

    def mark_failed(self, event_id: str, error: str) -> None:
        delay = min(300, 5 * (2 ** min(6, 3)))
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE support_agent.agent_work_event_outbox
                    SET last_error = %s,
                        available_at = now() + (%s || ' seconds')::interval,
                        locked_by = NULL,
                        locked_until = NULL
                    WHERE event_id = %s
                    """,
                    ((error or "")[:400], str(delay), event_id),
                )
            conn.commit()

    def pending_count(self) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT count(*) AS c FROM support_agent.agent_work_event_outbox
                    WHERE delivered_at IS NULL
                    """
                )
                row = cur.fetchone()
        return int(row["c"] if row else 0)

    def ready(self) -> bool:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT 1 FROM support_agent.agent_work_event_outbox LIMIT 1"
                    )
            return True
        except Exception:
            return False


_MEMORY = MemoryTelemetryOutbox()
_SCHEMA_READY = False
_SCHEMA_LOCK = threading.Lock()


def memory_telemetry_outbox() -> MemoryTelemetryOutbox:
    """Process-local outbox used when Postgres is unavailable."""
    return _MEMORY


def _postgres_dsn() -> str:
    return (
        os.getenv("SUPPORT_AGENT_POSTGRES_DSN")
        or os.getenv("SUPPORT_AGENT_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or ""
    ).strip()


def ensure_telemetry_schema() -> bool:
    """Apply support-agent migrations so the outbox table exists (idempotent)."""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return True
    dsn = _postgres_dsn()
    if not dsn:
        return False
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return True
        try:
            import psycopg

            from am_support_agent.stores.migrations import apply_migrations

            with psycopg.connect(dsn) as conn:
                apply_migrations(conn)
                conn.commit()
            _SCHEMA_READY = True
            return True
        except Exception:
            return False


def build_telemetry_outbox() -> TelemetryOutbox:
    dsn = _postgres_dsn()
    provider = (os.getenv("SUPPORT_AGENT_TELEMETRY_OUTBOX") or "").strip().lower()
    if provider == "memory":
        return _MEMORY
    if dsn and provider != "off":
        ensure_telemetry_schema()
        try:
            return PostgresTelemetryOutbox(dsn)
        except Exception:
            return _MEMORY
    return _MEMORY


# keep import used for type checkers / readiness probes
_ = time
