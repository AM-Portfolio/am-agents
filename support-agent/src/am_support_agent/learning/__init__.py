"""Gated learning pipeline — durable episode/feedback capture; no auto-promotion."""

from __future__ import annotations

from typing import Any

from am_support_agent.adapters.security import Redactor
from am_support_agent.contracts.incident import IncidentEpisode, IncidentFeedbackEvent
from am_support_agent.observability.metrics import Metrics
from am_support_agent.ports.episodes import EpisodeStore, FeedbackStore
from am_support_agent.stores.episodes import build_episode_store, build_feedback_store

_EPISODES: EpisodeStore | None = None
_FEEDBACK: FeedbackStore | None = None
_METRICS: Metrics | None = None
_REDACTOR = Redactor()


def configure_learning(
    *,
    episodes: EpisodeStore | None = None,
    feedback: FeedbackStore | None = None,
    metrics: Metrics | None = None,
) -> None:
    """Wire stores from composition root (multi-replica safe when Postgres)."""
    global _EPISODES, _FEEDBACK, _METRICS
    _EPISODES = episodes
    _FEEDBACK = feedback
    if metrics is not None:
        _METRICS = metrics


def episode_store() -> EpisodeStore:
    global _EPISODES
    if _EPISODES is None:
        _EPISODES = build_episode_store()
    return _EPISODES


def feedback_store() -> FeedbackStore:
    global _FEEDBACK
    if _FEEDBACK is None:
        _FEEDBACK = build_feedback_store()
    return _FEEDBACK


def promotion_allowed(*, human_approved: bool, offline_eval_passed: bool) -> bool:
    """Hard gate: both human approval and offline eval required."""
    return bool(human_approved and offline_eval_passed)


def ingest_feedback_event(event: dict[str, Any]) -> dict[str, Any]:
    """Accept a feedback event for offline evaluation (never auto-promotes)."""
    nested = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    payload = {
        k: v
        for k, v in event.items()
        if k
        not in {
            "notes",
            "labels",
            "payload",
            "episode_id",
            "tracking_id",
            "run_ref",
            "kind",
            "rating",
            "idempotency_key",
        }
    }
    payload.update(nested)
    fb = IncidentFeedbackEvent(
        episode_id=str(event.get("episode_id") or ""),
        tracking_id=str(event.get("tracking_id") or ""),
        run_ref=str(event.get("run_ref") or ""),
        kind=str(event.get("kind") or "outcome"),
        rating=str(event.get("rating") or ""),
        labels=list(event.get("labels") or []),
        notes=str(event.get("notes") or ""),
        payload=_REDACTOR.redact_dict(payload),
        auto_promote=False,
        idempotency_key=(
            str(event["idempotency_key"]) if event.get("idempotency_key") else None
        ),
    )
    store = feedback_store()
    existing = (
        store.get_by_idempotency(fb.idempotency_key) if fb.idempotency_key else None
    )
    stored = store.append(fb)
    if _METRICS is not None:
        _METRICS.observe_feedback(result="conflict" if existing else "write")
    if stored.episode_id:
        try:
            refs = [
                e.feedback_id
                for e in store.list_for_episode(stored.episode_id)
                if e.feedback_id
            ]
            episode_store().update_outcome(
                stored.episode_id,
                outcome=str(event.get("outcome") or "hitl_recorded"),
                human_feedback_refs=refs,
            )
            if _METRICS is not None:
                _METRICS.observe_episode(result="outcome")
        except KeyError:
            if _METRICS is not None:
                _METRICS.observe_episode(result="failure")
    return {
        "accepted": True,
        "auto_promote": False,
        "feedback_id": stored.feedback_id,
        "episode_id": stored.episode_id,
        "event_keys": sorted(event.keys()),
        "next": "evaluation → candidates → promotion gate",
    }


def persist_episode(episode: IncidentEpisode) -> IncidentEpisode:
    """Redact then upsert (idempotent on tracking_id+run_ref / episode_id)."""
    body = json_loads_redacted(episode)
    store = episode_store()
    prior = None
    if body.episode_id:
        prior = store.get(body.episode_id)
    if prior is None and body.tracking_id:
        prior = store.get_by_tracking_run(
            tracking_id=body.tracking_id,
            run_ref=body.run_ref or body.tracking_id,
        )
    try:
        stored = store.upsert(body)
    except Exception:
        if _METRICS is not None:
            _METRICS.observe_episode(result="failure")
        raise
    if _METRICS is not None:
        _METRICS.observe_episode(result="conflict" if prior else "write")
    return stored


def json_loads_redacted(episode: IncidentEpisode) -> IncidentEpisode:
    data = episode.model_dump(mode="json")
    if isinstance(data.get("context"), dict):
        ctx = data["context"]
        if isinstance(ctx.get("alert"), dict):
            ctx["alert"] = _REDACTOR.redact_dict(ctx["alert"])
        observe = ctx.get("observe") or []
        if isinstance(observe, list):
            redacted_obs = []
            for item in observe:
                if isinstance(item, dict):
                    copy = dict(item)
                    if isinstance(copy.get("data"), dict):
                        copy["data"] = _REDACTOR.redact_dict(copy["data"])
                    if isinstance(copy.get("summary"), str):
                        copy["summary"] = _REDACTOR.redact_text(copy["summary"])
                    redacted_obs.append(copy)
                else:
                    redacted_obs.append(item)
            ctx["observe"] = redacted_obs
    if isinstance(data.get("actions"), list):
        data["actions"] = [
            _REDACTOR.redact_dict(a) if isinstance(a, dict) else a for a in data["actions"]
        ]
    return IncidentEpisode.model_validate(data)


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
        "episodes": episode_store().status(),
        "feedback": feedback_store().status(),
    }


__all__ = [
    "configure_learning",
    "episode_store",
    "feedback_store",
    "ingest_feedback_event",
    "learning_status",
    "persist_episode",
    "promotion_allowed",
]
