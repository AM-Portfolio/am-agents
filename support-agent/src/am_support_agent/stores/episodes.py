"""In-memory episodic + feedback stores (Postgres later; Qdrant deferred)."""

from __future__ import annotations

import threading
from typing import Any

from am_support_agent.contracts.incident import (
    IncidentEpisode,
    IncidentFeedbackEvent,
    MemoryQuery,
)
from am_support_agent.ports.clock import SystemClock, UuidGenerator


class MemoryEpisodeStore:
    name = "memory-episodes"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, IncidentEpisode] = {}
        self._ids = UuidGenerator()
        self._clock = SystemClock()

    def status(self) -> dict[str, Any]:
        return {"name": self.name, "wired": True, "count": len(self._items)}

    def append(self, episode: IncidentEpisode) -> IncidentEpisode:
        with self._lock:
            if not episode.episode_id:
                episode = episode.model_copy(update={"episode_id": self._ids.new_id("ep-")})
            if not episode.created_at:
                episode = episode.model_copy(update={"created_at": self._clock.now_iso()})
            self._items[episode.episode_id] = episode
            return episode

    def get(self, episode_id: str) -> IncidentEpisode | None:
        return self._items.get(episode_id)

    def query(self, q: MemoryQuery) -> list[IncidentEpisode]:
        hits: list[IncidentEpisode] = []
        for ep in self._items.values():
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
                labels = alert.get("labels") if isinstance(alert.get("labels"), dict) else {}
                if any(labels.get(k) != v for k, v in q.labels.items()):
                    continue
            hits.append(ep)
            if len(hits) >= q.limit:
                break
        return hits


class MemoryFeedbackStore:
    name = "memory-feedback"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: list[IncidentFeedbackEvent] = []

    def status(self) -> dict[str, Any]:
        return {"name": self.name, "wired": True, "count": len(self._items)}

    def append(self, event: IncidentFeedbackEvent) -> IncidentFeedbackEvent:
        event = event.model_copy(update={"auto_promote": False})
        with self._lock:
            self._items.append(event)
            return event

    def list_for_episode(self, episode_id: str) -> list[IncidentFeedbackEvent]:
        return [e for e in self._items if e.episode_id == episode_id]
