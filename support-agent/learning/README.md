# Learning and feedback (gated)

Learning is **offline + gated**. Code hard-blocks auto-promotion.

## Implementation

| Path | Role | Status |
|------|------|--------|
| `src/am_support_agent/learning/` | `promotion_allowed`, `ingest_feedback_event` | ✅ gate helpers |
| `learning/feedback/` | Ingest FeedbackEvent | 📄 (API via A2A `feedback` + store) |
| `learning/evaluation/` | Offline suites / scorers | 📄 |
| `learning/candidates/` | Proposed prompt/policy/playbook refs | 📄 |
| `learning/promotion/` | Gate + audit trail | ✅ `promotion_allowed()` |

## Pipeline

```text
FeedbackEvent → candidates/ → evaluation/ → promotion/ → catalog or policy update
```

## Rules

1. No live self-modification of Tool / DB / UI Test agent code or runtime config.
2. No automatic production prompt/policy promotion.
3. Candidates require offline eval + human promotion approval.
4. Feedback storage is platform-owned (TaskRunStore feedback), not specialist APIs.
