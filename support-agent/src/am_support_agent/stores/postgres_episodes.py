"""Postgres episode + feedback stores — dedicated support_agent tables."""

from __future__ import annotations

import json
import threading
from typing import Any

from am_support_agent.contracts.incident import (
    IncidentEpisode,
    IncidentFeedbackEvent,
    MemoryQuery,
    episode_id_for,
)
from am_support_agent.ports.clock import SystemClock, UuidGenerator
from am_support_agent.stores.migrations import apply_migrations


def _alert_fields(episode: IncidentEpisode) -> tuple[str, str, str, dict[str, str]]:
    ctx = episode.context
    alert = (ctx.alert if ctx else None) or {}
    labels = alert.get("labels") if isinstance(alert.get("labels"), dict) else {}
    return (
        str(alert.get("service") or ""),
        str(alert.get("env") or alert.get("environment") or ""),
        str(alert.get("fingerprint") or ""),
        {str(k): str(v) for k, v in labels.items()},
    )


class PostgresEpisodeStore:
    name = "postgres-episodes"

    def __init__(self, dsn: str) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
            from psycopg.types.json import Jsonb
        except ImportError as exc:
            raise RuntimeError(
                "Episode Postgres store requires psycopg. "
                "Install with: pip install 'am-support-agent[postgres]'"
            ) from exc
        self._psycopg = psycopg
        self._Jsonb = Jsonb
        self._dsn = dsn
        self._lock = threading.RLock()
        self._conn = psycopg.connect(dsn, row_factory=dict_row)
        self._conn.autocommit = False
        self._clock = SystemClock()
        self._ids = UuidGenerator()
        apply_migrations(self._conn)

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "wired": True,
            "durable": True,
            "backend": "postgres",
            "ready": self.ready(),
        }

    def ready(self) -> bool:
        try:
            with self._lock:
                with self._conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
                self._conn.commit()
            return True
        except Exception:  # noqa: BLE001
            try:
                self._conn.rollback()
            except Exception:  # noqa: BLE001
                pass
            return False

    def append(self, episode: IncidentEpisode) -> IncidentEpisode:
        return self.upsert(episode)

    def upsert(self, episode: IncidentEpisode) -> IncidentEpisode:
        tracking = episode.tracking_id
        run_ref = episode.run_ref or tracking
        if not episode.episode_id:
            episode = episode.model_copy(
                update={"episode_id": episode_id_for(tracking_id=tracking, run_ref=run_ref)}
            )
        now = self._clock.now_iso()
        if not episode.created_at:
            episode = episode.model_copy(update={"created_at": now})
        episode = episode.model_copy(update={"updated_at": now})
        service, env, fingerprint, labels = _alert_fields(episode)
        body = json.loads(episode.model_dump_json())
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO support_agent.incident_episodes (
                        episode_id, tracking_id, run_ref, service, env, fingerprint,
                        labels, decision, outcome, verify_status, body_json, provenance,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s::timestamptz, %s::timestamptz
                    )
                    ON CONFLICT (episode_id) DO NOTHING
                    RETURNING episode_id
                    """,
                    (
                        episode.episode_id,
                        tracking,
                        run_ref,
                        service,
                        env,
                        fingerprint,
                        self._Jsonb(labels),
                        episode.decision,
                        episode.outcome,
                        episode.verify_status,
                        self._Jsonb(body),
                        self._Jsonb(episode.provenance),
                        episode.created_at,
                        episode.updated_at,
                    ),
                )
                inserted = cur.fetchone()
                if inserted is None:
                    cur.execute(
                        """
                        SELECT body_json FROM support_agent.incident_episodes
                        WHERE episode_id = %s
                        """,
                        (episode.episode_id,),
                    )
                    row = cur.fetchone()
                    self._conn.commit()
                    return IncidentEpisode.model_validate(row["body_json"])
            self._conn.commit()
        return episode

    def get(self, episode_id: str) -> IncidentEpisode | None:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT body_json FROM support_agent.incident_episodes
                    WHERE episode_id = %s
                    """,
                    (episode_id,),
                )
                row = cur.fetchone()
            self._conn.commit()
        if not row:
            return None
        return IncidentEpisode.model_validate(row["body_json"])

    def get_by_tracking_run(
        self, *, tracking_id: str, run_ref: str
    ) -> IncidentEpisode | None:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT body_json FROM support_agent.incident_episodes
                    WHERE tracking_id = %s AND run_ref = %s
                    """,
                    (tracking_id, run_ref),
                )
                row = cur.fetchone()
            self._conn.commit()
        if not row:
            return None
        return IncidentEpisode.model_validate(row["body_json"])

    def query(self, q: MemoryQuery) -> list[IncidentEpisode]:
        if not q.has_discriminating_filter():
            return []
        clauses: list[str] = []
        params: list[Any] = []
        if q.service:
            clauses.append("service = %s")
            params.append(q.service)
        if q.env:
            clauses.append("env = %s")
            params.append(q.env)
        if q.fingerprint:
            clauses.append("fingerprint = %s")
            params.append(q.fingerprint)
        if q.labels:
            clauses.append("labels @> %s::jsonb")
            params.append(json.dumps(q.labels))
        where = " AND ".join(clauses)
        params.append(max(1, min(q.limit, 100)))
        sql = f"""
            SELECT body_json FROM support_agent.incident_episodes
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT %s
        """
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
            self._conn.commit()
        return [IncidentEpisode.model_validate(r["body_json"]) for r in rows]

    def update_outcome(
        self,
        episode_id: str,
        *,
        outcome: str,
        verify_status: str = "",
        evidence: list[dict[str, Any]] | None = None,
        human_feedback_refs: list[str] | None = None,
    ) -> IncidentEpisode:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT body_json FROM support_agent.incident_episodes
                    WHERE episode_id = %s FOR UPDATE
                    """,
                    (episode_id,),
                )
                row = cur.fetchone()
                if not row:
                    raise KeyError(f"unknown episode_id: {episode_id}")
                ep = IncidentEpisode.model_validate(row["body_json"])
                updates: dict[str, Any] = {
                    "outcome": outcome,
                    "updated_at": self._clock.now_iso(),
                }
                if verify_status:
                    updates["verify_status"] = verify_status
                if evidence is not None:
                    from am_support_agent.contracts.schemas import EvidenceItem

                    updates["evidence"] = [
                        EvidenceItem.model_validate(item)
                        if isinstance(item, dict)
                        else item
                        for item in evidence
                    ]
                if human_feedback_refs is not None:
                    updates["human_feedback_refs"] = list(human_feedback_refs)
                ep = ep.model_copy(update=updates)
                body = json.loads(ep.model_dump_json())
                cur.execute(
                    """
                    UPDATE support_agent.incident_episodes
                    SET outcome = %s,
                        verify_status = %s,
                        body_json = %s,
                        updated_at = %s::timestamptz
                    WHERE episode_id = %s
                    """,
                    (
                        ep.outcome,
                        ep.verify_status,
                        self._Jsonb(body),
                        ep.updated_at,
                        episode_id,
                    ),
                )
            self._conn.commit()
        return ep

    def purge_terminal_before(self, cutoff_iso: str, *, limit: int = 500) -> int:
        batch = max(1, min(limit, 5000))
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM support_agent.incident_episodes
                    WHERE episode_id IN (
                        SELECT episode_id FROM support_agent.incident_episodes
                        WHERE created_at < %s::timestamptz
                          AND outcome <> ''
                          AND outcome <> 'pending'
                        ORDER BY created_at ASC
                        LIMIT %s
                    )
                    """,
                    (cutoff_iso, batch),
                )
                deleted = cur.rowcount
            self._conn.commit()
        return int(deleted or 0)


class PostgresFeedbackStore:
    name = "postgres-feedback"

    def __init__(self, dsn: str) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
            from psycopg.types.json import Jsonb
        except ImportError as exc:
            raise RuntimeError(
                "Feedback Postgres store requires psycopg. "
                "Install with: pip install 'am-support-agent[postgres]'"
            ) from exc
        self._psycopg = psycopg
        self._Jsonb = Jsonb
        self._dsn = dsn
        self._lock = threading.RLock()
        self._conn = psycopg.connect(dsn, row_factory=dict_row)
        self._conn.autocommit = False
        self._clock = SystemClock()
        self._ids = UuidGenerator()
        apply_migrations(self._conn)

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "wired": True,
            "durable": True,
            "backend": "postgres",
            "ready": self.ready(),
        }

    def ready(self) -> bool:
        try:
            with self._lock:
                with self._conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
                self._conn.commit()
            return True
        except Exception:  # noqa: BLE001
            try:
                self._conn.rollback()
            except Exception:  # noqa: BLE001
                pass
            return False

    def append(self, event: IncidentFeedbackEvent) -> IncidentFeedbackEvent:
        event = event.model_copy(update={"auto_promote": False})
        if not event.feedback_id:
            event = event.model_copy(update={"feedback_id": self._ids.new_id("fb-")})
        if not event.created_at:
            event = event.model_copy(update={"created_at": self._clock.now_iso()})
        with self._lock:
            with self._conn.cursor() as cur:
                if event.idempotency_key:
                    cur.execute(
                        """
                        SELECT feedback_id, episode_id, tracking_id, run_ref, kind,
                               rating, labels, notes, payload, auto_promote,
                               idempotency_key, created_at
                        FROM support_agent.incident_feedback_events
                        WHERE idempotency_key = %s
                        """,
                        (event.idempotency_key,),
                    )
                    existing = cur.fetchone()
                    if existing:
                        self._conn.commit()
                        return self._row_to_event(existing)
                cur.execute(
                    """
                    INSERT INTO support_agent.incident_feedback_events (
                        feedback_id, episode_id, tracking_id, run_ref, kind, rating,
                        labels, notes, payload, auto_promote, idempotency_key, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, FALSE, %s, %s::timestamptz
                    )
                    """,
                    (
                        event.feedback_id,
                        event.episode_id,
                        event.tracking_id,
                        event.run_ref,
                        event.kind,
                        event.rating,
                        self._Jsonb(event.labels),
                        event.notes,
                        self._Jsonb(event.payload),
                        event.idempotency_key,
                        event.created_at,
                    ),
                )
            self._conn.commit()
        return event

    def get_by_idempotency(self, key: str) -> IncidentFeedbackEvent | None:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT feedback_id, episode_id, tracking_id, run_ref, kind,
                           rating, labels, notes, payload, auto_promote,
                           idempotency_key, created_at
                    FROM support_agent.incident_feedback_events
                    WHERE idempotency_key = %s
                    """,
                    (key,),
                )
                row = cur.fetchone()
            self._conn.commit()
        return self._row_to_event(row) if row else None

    def list_for_episode(self, episode_id: str) -> list[IncidentFeedbackEvent]:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT feedback_id, episode_id, tracking_id, run_ref, kind,
                           rating, labels, notes, payload, auto_promote,
                           idempotency_key, created_at
                    FROM support_agent.incident_feedback_events
                    WHERE episode_id = %s
                    ORDER BY created_at ASC
                    """,
                    (episode_id,),
                )
                rows = cur.fetchall()
            self._conn.commit()
        return [self._row_to_event(r) for r in rows]

    def purge_terminal_before(self, cutoff_iso: str, *, limit: int = 500) -> int:
        batch = max(1, min(limit, 5000))
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM support_agent.incident_feedback_events
                    WHERE feedback_id IN (
                        SELECT feedback_id FROM support_agent.incident_feedback_events
                        WHERE created_at < %s::timestamptz
                        ORDER BY created_at ASC
                        LIMIT %s
                    )
                    """,
                    (cutoff_iso, batch),
                )
                deleted = cur.rowcount
            self._conn.commit()
        return int(deleted or 0)

    def _row_to_event(self, row: dict[str, Any]) -> IncidentFeedbackEvent:
        created = row.get("created_at")
        return IncidentFeedbackEvent(
            feedback_id=str(row.get("feedback_id") or ""),
            episode_id=str(row.get("episode_id") or ""),
            tracking_id=str(row.get("tracking_id") or ""),
            run_ref=str(row.get("run_ref") or ""),
            kind=str(row.get("kind") or "outcome"),
            rating=str(row.get("rating") or ""),
            labels=list(row.get("labels") or []),
            notes=str(row.get("notes") or ""),
            payload=dict(row.get("payload") or {}),
            auto_promote=False,
            idempotency_key=row.get("idempotency_key"),
            created_at=created.isoformat() if hasattr(created, "isoformat") else str(created or ""),
        )


__all__ = ["PostgresEpisodeStore", "PostgresFeedbackStore"]
