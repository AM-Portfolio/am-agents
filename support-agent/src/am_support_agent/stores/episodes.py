"""Episode + feedback stores (memory default; Postgres for production)."""

from __future__ import annotations

import os
import threading
from typing import Any

from am_support_agent.contracts.incident import (
    IncidentEpisode,
    IncidentFeedbackEvent,
    MemoryQuery,
    episode_id_for,
)
from am_support_agent.ports.clock import SystemClock, UuidGenerator
from am_support_agent.ports.episodes import EpisodeStore, FeedbackStore


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


class MemoryEpisodeStore:
    name = "memory-episodes"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._items: dict[str, IncidentEpisode] = {}
        self._by_tracking_run: dict[tuple[str, str], str] = {}
        self._ids = UuidGenerator()
        self._clock = SystemClock()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "name": self.name,
                "wired": True,
                "durable": False,
                "backend": "memory",
                "count": len(self._items),
            }

    def ready(self) -> bool:
        return True

    def append(self, episode: IncidentEpisode) -> IncidentEpisode:
        return self.upsert(episode)

    def upsert(self, episode: IncidentEpisode) -> IncidentEpisode:
        with self._lock:
            tracking = episode.tracking_id
            run_ref = episode.run_ref or tracking
            if not episode.episode_id:
                existing_id = self._by_tracking_run.get((tracking, run_ref))
                episode = episode.model_copy(
                    update={
                        "episode_id": existing_id
                        or episode_id_for(tracking_id=tracking, run_ref=run_ref)
                    }
                )
            now = self._clock.now_iso()
            if not episode.created_at:
                episode = episode.model_copy(update={"created_at": now})
            episode = episode.model_copy(update={"updated_at": now})
            prior = self._items.get(episode.episode_id)
            if prior is not None:
                # Idempotent create: keep first body, allow outcome merge later.
                return prior
            self._items[episode.episode_id] = episode
            self._by_tracking_run[(tracking, run_ref)] = episode.episode_id
            return episode

    def get(self, episode_id: str) -> IncidentEpisode | None:
        with self._lock:
            return self._items.get(episode_id)

    def get_by_tracking_run(
        self, *, tracking_id: str, run_ref: str
    ) -> IncidentEpisode | None:
        with self._lock:
            eid = self._by_tracking_run.get((tracking_id, run_ref))
            return self._items.get(eid) if eid else None

    def query(self, q: MemoryQuery) -> list[IncidentEpisode]:
        if not q.has_discriminating_filter():
            return []
        with self._lock:
            hits: list[IncidentEpisode] = []
            # Newest first
            items = sorted(
                self._items.values(),
                key=lambda ep: ep.created_at or "",
                reverse=True,
            )
            for ep in items:
                ctx = ep.context
                if not ctx:
                    continue
                alert = ctx.alert or {}
                if q.service and str(alert.get("service") or "") != q.service:
                    continue
                if q.env and str(alert.get("env") or alert.get("environment") or "") != q.env:
                    continue
                if q.fingerprint and str(alert.get("fingerprint") or "") != q.fingerprint:
                    continue
                if q.labels:
                    labels = (
                        alert.get("labels")
                        if isinstance(alert.get("labels"), dict)
                        else {}
                    )
                    if any(labels.get(k) != v for k, v in q.labels.items()):
                        continue
                hits.append(ep)
                if len(hits) >= q.limit:
                    break
            return hits

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
            ep = self._items.get(episode_id)
            if ep is None:
                raise KeyError(f"unknown episode_id: {episode_id}")
            updates: dict[str, Any] = {
                "outcome": outcome,
                "updated_at": self._clock.now_iso(),
            }
            if verify_status:
                updates["verify_status"] = verify_status
            if evidence is not None:
                from am_support_agent.contracts.schemas import EvidenceItem

                updates["evidence"] = [
                    EvidenceItem.model_validate(item) if isinstance(item, dict) else item
                    for item in evidence
                ]
            if human_feedback_refs is not None:
                updates["human_feedback_refs"] = list(human_feedback_refs)
            ep = ep.model_copy(update=updates)
            self._items[episode_id] = ep
            return ep

    def purge_terminal_before(self, cutoff_iso: str, *, limit: int = 500) -> int:
        with self._lock:
            doomed = [
                eid
                for eid, ep in self._items.items()
                if (ep.created_at or "") < cutoff_iso
                and ep.outcome not in {"", "pending"}
            ][: max(1, min(limit, 5000))]
            for eid in doomed:
                ep = self._items.pop(eid, None)
                if ep is None:
                    continue
                key = (ep.tracking_id, ep.run_ref or ep.tracking_id)
                if self._by_tracking_run.get(key) == eid:
                    self._by_tracking_run.pop(key, None)
            return len(doomed)


class MemoryFeedbackStore:
    name = "memory-feedback"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._items: list[IncidentFeedbackEvent] = []
        self._by_idem: dict[str, IncidentFeedbackEvent] = {}
        self._ids = UuidGenerator()
        self._clock = SystemClock()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "name": self.name,
                "wired": True,
                "durable": False,
                "backend": "memory",
                "count": len(self._items),
            }

    def ready(self) -> bool:
        return True

    def append(self, event: IncidentFeedbackEvent) -> IncidentFeedbackEvent:
        event = event.model_copy(update={"auto_promote": False})
        with self._lock:
            if event.idempotency_key and event.idempotency_key in self._by_idem:
                return self._by_idem[event.idempotency_key]
            if not event.feedback_id:
                event = event.model_copy(
                    update={"feedback_id": self._ids.new_id("fb-")}
                )
            if not event.created_at:
                event = event.model_copy(update={"created_at": self._clock.now_iso()})
            self._items.append(event)
            if event.idempotency_key:
                self._by_idem[event.idempotency_key] = event
            return event

    def get_by_idempotency(self, key: str) -> IncidentFeedbackEvent | None:
        with self._lock:
            return self._by_idem.get(key)

    def list_for_episode(self, episode_id: str) -> list[IncidentFeedbackEvent]:
        with self._lock:
            return [e for e in self._items if e.episode_id == episode_id]

    def purge_terminal_before(self, cutoff_iso: str, *, limit: int = 500) -> int:
        with self._lock:
            keep: list[IncidentFeedbackEvent] = []
            removed = 0
            for event in self._items:
                if (
                    removed < max(1, min(limit, 5000))
                    and (event.created_at or "") < cutoff_iso
                ):
                    removed += 1
                    if event.idempotency_key:
                        self._by_idem.pop(event.idempotency_key, None)
                    continue
                keep.append(event)
            self._items = keep
            return removed


def _dsn() -> str:
    return (
        os.getenv("SUPPORT_AGENT_DATABASE_URL", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
    )


def _backend(name: str, fallback_env: str = "SUPPORT_AGENT_RUNSTORE") -> str:
    raw = os.getenv(name, "").strip().lower()
    if raw:
        return raw
    return os.getenv(fallback_env, "memory").strip().lower() or "memory"


_cached_episode_store: EpisodeStore | None = None
_cached_feedback_store: FeedbackStore | None = None
_store_lock = threading.RLock()


def build_episode_store() -> EpisodeStore:
    global _cached_episode_store
    backend = _backend("SUPPORT_AGENT_EPISODE_STORE")
    if backend == "memory":
        return MemoryEpisodeStore()
    if backend == "postgres":
        with _store_lock:
            if _cached_episode_store is None:
                dsn = _dsn()
                if not dsn:
                    raise RuntimeError(
                        "SUPPORT_AGENT_EPISODE_STORE=postgres requires SUPPORT_AGENT_DATABASE_URL"
                    )
                from am_support_agent.stores.postgres_episodes import PostgresEpisodeStore

                _cached_episode_store = PostgresEpisodeStore(dsn)
            return _cached_episode_store
    raise ValueError(f"unsupported SUPPORT_AGENT_EPISODE_STORE: {backend}")


def build_feedback_store() -> FeedbackStore:
    global _cached_feedback_store
    backend = _backend("SUPPORT_AGENT_FEEDBACK_STORE")
    if backend == "memory":
        return MemoryFeedbackStore()
    if backend == "postgres":
        with _store_lock:
            if _cached_feedback_store is None:
                dsn = _dsn()
                if not dsn:
                    raise RuntimeError(
                        "SUPPORT_AGENT_FEEDBACK_STORE=postgres requires SUPPORT_AGENT_DATABASE_URL"
                    )
                from am_support_agent.stores.postgres_episodes import PostgresFeedbackStore

                _cached_feedback_store = PostgresFeedbackStore(dsn)
            return _cached_feedback_store
    raise ValueError(f"unsupported SUPPORT_AGENT_FEEDBACK_STORE: {backend}")


__all__ = [
    "EpisodeStore",
    "FeedbackStore",
    "MemoryEpisodeStore",
    "MemoryFeedbackStore",
    "build_episode_store",
    "build_feedback_store",
]
