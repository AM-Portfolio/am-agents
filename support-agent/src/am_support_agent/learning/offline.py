"""Offline evaluation / candidates — audited, never auto-promoted."""

from __future__ import annotations

import json
from typing import Any

from am_support_agent.learning import episode_store, feedback_store, promotion_allowed
from am_support_agent.ports.clock import SystemClock, UuidGenerator

_clock = SystemClock()
_ids = UuidGenerator()


def _metrics():
    from am_support_agent.learning import _METRICS

    return _METRICS


def evaluate_episode(episode_id: str) -> dict[str, Any]:
    """Score a terminal episode for candidate generation (offline only)."""
    ep = episode_store().get(episode_id)
    if ep is None:
        return {"ok": False, "error": "episode_not_found", "episode_id": episode_id}
    feedback = feedback_store().list_for_episode(episode_id)
    terminal = ep.outcome not in {"", "pending"}
    score = 0.0
    if terminal:
        score += 0.5
    if ep.decision:
        score += 0.2
    if feedback:
        score += 0.3
    evaluation = {
        "evaluation_id": _ids.new_id("eval-"),
        "episode_id": episode_id,
        "tracking_id": ep.tracking_id,
        "status": "scored" if terminal else "incomplete",
        "score": round(score, 3),
        "summary": {
            "decision": ep.decision,
            "outcome": ep.outcome,
            "feedback_count": len(feedback),
            "terminal": terminal,
        },
        "created_at": _clock.now_iso(),
    }
    candidate = None
    if terminal and score >= 0.7:
        candidate = {
            "candidate_id": _ids.new_id("cand-"),
            "evaluation_id": evaluation["evaluation_id"],
            "kind": "policy",
            "payload": {
                "source_episode": episode_id,
                "decision": ep.decision,
                "outcome": ep.outcome,
            },
            "status": "proposed",
            "created_at": _clock.now_iso(),
        }
    metrics = _metrics()
    if metrics is not None:
        metrics.observe_learning(kind="evaluation")
        if candidate:
            metrics.observe_learning(kind="candidate")
    return {
        "ok": True,
        "evaluation": evaluation,
        "candidate": candidate,
        "auto_promote": False,
        "promotion_allowed": False,
    }


def record_promotion(
    *,
    candidate_id: str,
    human_approved: bool,
    offline_eval_passed: bool,
    approved_by: str = "",
    notes: str = "",
) -> dict[str, Any]:
    allowed = promotion_allowed(
        human_approved=human_approved,
        offline_eval_passed=offline_eval_passed,
    )
    metrics = _metrics()
    if metrics is not None:
        metrics.observe_learning(
            kind="promotion_allowed" if allowed else "promotion_blocked"
        )
    return {
        "decision_id": _ids.new_id("promo-"),
        "candidate_id": candidate_id,
        "human_approved": human_approved,
        "offline_eval_passed": offline_eval_passed,
        "approved_by": approved_by,
        "notes": notes,
        "promoted": False,
        "allowed": allowed,
        "reason": (
            "promotion recorded for audit; live catalog writes remain gated"
            if allowed
            else "blocked: requires human_approved and offline_eval_passed"
        ),
        "created_at": _clock.now_iso(),
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Offline learning evaluation")
    parser.add_argument("episode_id")
    args = parser.parse_args(argv)
    print(json.dumps(evaluate_episode(args.episode_id), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
