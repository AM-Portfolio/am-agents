"""Episode and feedback store ports — durable memory for incident learning."""

from __future__ import annotations

from typing import Any, Protocol

from am_support_agent.contracts.incident import (
    IncidentEpisode,
    IncidentFeedbackEvent,
    MemoryQuery,
)


class EpisodeStore(Protocol):
    name: str

    def status(self) -> dict[str, Any]: ...

    def ready(self) -> bool: ...

    def append(self, episode: IncidentEpisode) -> IncidentEpisode: ...

    def upsert(self, episode: IncidentEpisode) -> IncidentEpisode: ...

    def get(self, episode_id: str) -> IncidentEpisode | None: ...

    def get_by_tracking_run(
        self, *, tracking_id: str, run_ref: str
    ) -> IncidentEpisode | None: ...

    def query(self, q: MemoryQuery) -> list[IncidentEpisode]: ...

    def update_outcome(
        self,
        episode_id: str,
        *,
        outcome: str,
        verify_status: str = "",
        evidence: list[dict[str, Any]] | None = None,
        human_feedback_refs: list[str] | None = None,
    ) -> IncidentEpisode: ...

    def purge_terminal_before(self, cutoff_iso: str, *, limit: int = 500) -> int: ...


class FeedbackStore(Protocol):
    name: str

    def status(self) -> dict[str, Any]: ...

    def ready(self) -> bool: ...

    def append(self, event: IncidentFeedbackEvent) -> IncidentFeedbackEvent: ...

    def get_by_idempotency(self, key: str) -> IncidentFeedbackEvent | None: ...

    def list_for_episode(self, episode_id: str) -> list[IncidentFeedbackEvent]: ...

    def purge_terminal_before(self, cutoff_iso: str, *, limit: int = 500) -> int: ...


__all__ = ["EpisodeStore", "FeedbackStore"]
