# Parity thresholds (Phase 3)

Support-agent runs **alongside** legacy `gateway/` + `platform_worker/`. Shadow
traffic compares replacement outputs to legacy results without side effects.

## Endpoint safety

| Endpoint | Allowed ops | Writes to specialists |
|----------|-------------|------------------------|
| `POST /v2/shadow` | `discover`, `plan` only | No (`execute` rejected with 400) |
| `GET /v2/canary` | config + rollback hint | No |
| `POST /v2/canary/decide` | sticky route decision | No |

## Canary modes

GrowthBook is the runtime source of truth when `GROWTHBOOK_ENABLED=true`.
Create a feature named `support-agent-route` (or set
`GROWTHBOOK_ROUTE_FEATURE_KEY`) with one of these values:

| Flag value | Route |
|------------|-------|
| `new`, `support`, `v2`, or boolean `true` | New support-agent |
| `legacy`, `off`, or boolean `false` | Legacy gateway |
| `shadow` | Shadow-only; live workflow starts return 409 |

Target using the SDK attributes `id`, `key`, `environment`, `service`, and
`workflow`. The SDK client is reused and refreshes its feature cache at runtime.
If GrowthBook or its SDK key is unavailable, routing fails closed to `legacy`.
`SUPPORT_AGENT_FORCE_LEGACY=true` always overrides GrowthBook.

Required runtime configuration:

- `GROWTHBOOK_ENABLED=true`
- `GROWTHBOOK_API_HOST=https://api.growthbook.asrax.in`
- `GROWTHBOOK_CLIENT_KEY` from a GrowthBook SDK Connection (Vault only)
- `GROWTHBOOK_ROUTE_FEATURE_KEY=support-agent-route`
- `GROWTHBOOK_CACHE_TTL_SECONDS=60`

When GrowthBook is disabled, the environment-based canary fallback remains:

| `SUPPORT_AGENT_CANARY_MODE` | Splitter (`/v2/canary/decide`) | Live workflow starts on this gateway |
|-----------------------------|-------------------------------|--------------------------------------|
| `off` (default) | `legacy` | Allowed (opt-in by calling v2) |
| `shadow` | `shadow` | **409** — use `/v2/shadow` only |
| `canary` | `support` if allowlist or percent bucket | Allowed only when selected |

Instant rollback: `SUPPORT_AGENT_FORCE_LEGACY=true` (or mode `off` at the
external router). Legacy `agent-platform` queue stays healthy; pause
`support-agent-v2` workers if needed.

Env:

- `SUPPORT_AGENT_CANARY_PERCENT` — 0–100 sticky hash share
- `SUPPORT_AGENT_CANARY_ALLOWLIST` — comma-separated tracking/demand ids

## Ignored volatile keys

These keys are excluded from structural comparison (see
`DEFAULT_IGNORED_KEYS` in `am_support_agent.parity`):

- `task_id`, `run_id`, `workflow_id`
- `created_at`, `updated_at`
- `latency_ms`

## Thresholds

| Mode | Constant | Gate |
|------|----------|------|
| Shadow discover/plan | `SHADOW_MATCH_THRESHOLD = 1.0` | Exact match after ignored keys (`matched` and `meets_threshold`) |
| Soft / experimental scoring | `SOFT_MATCH_THRESHOLD = 0.95` | Match-rate floor only; **not** used by `/v2/shadow` |

`ParityReport.match_rate` = matched leaf fields / compared leaf fields.
Missing keys on either side count as compared mismatches.

## Fixture corpus

Deterministic cases live under `tests/fixtures/parity/`. Each JSON file has:

```json
{
  "name": "tool_plan_happy",
  "legacy": { "...": "..." },
  "replacement": { "...": "..." },
  "expect_matched": true
}
```

CI loads every fixture via `tests/test_parity.py`. Add fixtures when a new
discover/plan (or validation) shape is promoted into shadow comparison.
