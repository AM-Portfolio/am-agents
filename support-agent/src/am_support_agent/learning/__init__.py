"""Gated learning pipeline — feedback + episode capture for canary; no auto-promotion."""

from __future__ import annotations

from typing import Any

from am_support_agent.contracts.incident import IncidentEpisode, IncidentFeedbackEvent
from am_support_agent.stores.episodes import MemoryEpisodeStore, MemoryFeedbackStore

_EPISODES = MemoryEpisodeStore()
_FEEDBACK = MemoryFeedbackStore()


def episode_store() -> MemoryEpisodeStore:
    return _EPISODES


def feedback_store() -> MemoryFeedbackStore:
    return _FEEDBACK


def promotion_allowed(*, human_approved: bool, offline_eval_passed: bool) -> bool:
    """Hard gate: both human approval and offline eval required."""
    return bool(human_approved and offline_eval_passed)


def ingest_feedback_event(event: dict[str, Any]) -> dict[str, Any]:
    """Accept a feedback event for offline evaluation (never auto-promotes)."""
    fb = IncidentFeedbackEvent(
        episode_id=str(event.get("episode_id") or ""),
        tracking_id=str(event.get("tracking_id") or ""),
        run_ref=str(event.get("run_ref") or ""),
        kind=str(event.get("kind") or "outcome"),
        labels=list(event.get("labels") or []),
        notes=str(event.get("notes") or ""),
        payload={k: v for k, v in event.items() if k not in {"notes", "labels"}},
        auto_promote=False,
    )
    stored = _FEEDBACK.append(fb)
    return {
        "accepted": True,
        "auto_promote": False,
        "episode_id": stored.episode_id,
        "event_keys": sorted(event.keys()),
        "next": "evaluation → candidates → promotion gate",
    }


def persist_episode(episode: IncidentEpisode) -> IncidentEpisode:
    return _EPISODES.append(episode)


def learning_status() -> dict[str, Any]:
    return {
        "auto_promote": False,
        "pipeline": [
            "feedback",
            "evaluation",
            "candidates",
            "promotion",
        ],
        "rule": "never auto-live; human + offline eval required",
        "episodes": _EPISODES.status(),
        "feedback": _FEEDBACK.status(),
    }


__all__ = [
    "episode_store",
    "feedback_store",
    "ingest_feedback_event",
    "learning_status",
    "persist_episode",
    "promotion_allowed",
]
