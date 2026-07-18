# Learning and feedback (gated)

Learning is **offline + gated**. Code hard-blocks auto-promotion.

## Implementation

| Path | Role | Status |
|------|------|--------|
| `src/am_support_agent/learning/` | `promotion_allowed`, `ingest_feedback_event`, `persist_episode` | ✅ |
| `src/am_support_agent/learning/offline.py` | Evaluate episode → candidate; record promotion audit | ✅ never auto-live |
| `stores/postgres_episodes.py` | Durable episode + feedback | ✅ |
| `stores/migrations.py` | `learning_*` / `promotion_decisions` tables | ✅ schema ready |

## Pipeline

```text
FeedbackEvent → offline evaluate → candidates → human + offline gate → controlled promotion
```

```bash
python -m am_support_agent.learning.offline <episode_id>
```

## Rules

1. No live self-modification of Tool / DB / UI Test agent code or runtime config.
2. No automatic production prompt/policy promotion (`promoted` is always false in code).
3. Candidates require offline eval + human promotion approval.
4. Feedback/episode storage is support-agent Postgres (not specialist APIs); never written into `task_runs` or legacy `agent_runs`.
