"""Retention cleanup for terminal incident episodes and feedback."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from am_support_agent.stores.episodes import build_episode_store, build_feedback_store

_TERMINAL_DEFAULT_DAYS = 90


def retention_days() -> int:
    raw = os.getenv("SUPPORT_AGENT_EPISODE_RETENTION_DAYS", "").strip()
    if not raw:
        return _TERMINAL_DEFAULT_DAYS
    try:
        return max(1, int(raw))
    except ValueError:
        return _TERMINAL_DEFAULT_DAYS


def cutoff_iso(*, days: int | None = None) -> str:
    window = days if days is not None else retention_days()
    return (datetime.now(timezone.utc) - timedelta(days=window)).isoformat()


def cleanup_memory(*, days: int | None = None, batch_size: int = 500) -> dict[str, Any]:
    """Delete terminal episodes/feedback older than retention window (bounded batches)."""
    cutoff = cutoff_iso(days=days)
    episodes = build_episode_store()
    feedback = build_feedback_store()
    # Feedback first (no FK enforced, but keeps orphan noise down).
    fb_deleted = feedback.purge_terminal_before(cutoff, limit=batch_size)
    ep_deleted = episodes.purge_terminal_before(cutoff, limit=batch_size)
    return {
        "cutoff": cutoff,
        "retention_days": days if days is not None else retention_days(),
        "episodes_deleted": ep_deleted,
        "feedback_deleted": fb_deleted,
        "note": "learning_evaluations / promotion_decisions are retained longer and not purged here",
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Purge aged terminal incident memory")
    parser.add_argument("--days", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args(argv)
    print(json.dumps(cleanup_memory(days=args.days, batch_size=args.batch_size), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
