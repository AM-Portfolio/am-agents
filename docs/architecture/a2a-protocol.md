# A2A Protocol

**Status:** Phase 0 contract specification (Markdown schemas only)  
**Related:** [Agent Platform](agent-platform.md) · [Execution flow](execution-flow.md) · [Module contracts](../../support-agent/contracts/README.md)

## Goal

Define a stable agent-to-agent surface that the Platform Orchestrator uses. Specialist agents keep their existing HTTP APIs. **Adapters synthesize** operations that specialists do not expose natively.

## Platform-facing operations

| Op | Purpose | Tool Agent today | DB Agent today | UI Test today | Adapter compensation |
|----|---------|------------------|----------------|---------------|----------------------|
| `discover` | Capability / agent card | `GET /health` + tool manifests | `GET /health` + registry | `GET /health` + OpenAPI | Static registry + health → agent card |
| `plan` | Dry-run / step plan | `POST /api/v1/tools/plan` (+ stream) | `POST /api/v1/db/plan` | none | UI: synthesize plan from request body |
| `execute` | Run work | `POST /api/v1/tools/execute` (+ stream) | `POST /api/v1/db/execute` | `POST /api/v1/test/run` | Map response → platform `task_id` / `run_id` |
| `stream` | Progress events | SSE `/…/stream` | limited / none | status polling | UI: poll `/api/v1/test/status/{id}` → event stream |
| `status` | Current state | no durable run store | no durable run store | `GET /api/v1/test/status/{id}` (in-memory) | Tool/DB: correlation id + last response; UI: best-effort, no multi-replica assumption |
| `cancel` | Stop work | not native | not native | not native | Cancel **platform** task / Temporal workflow; specialist best-effort only |
| `feedback` | Outcome / quality signal | not native | not native | not native | Persist only in platform RunStore / feedback store |

## Routing policy

1. **Prefer Tool Agent** for data, infra tools, observability queries, vault, kafka, mongo, postgres, grafana, etc.
2. **DB Agent** only when capability tag `legacy.db-agent` is explicitly requested or a migration allowlist requires it.
3. **UI Test Agent** only for browser / visual / Playwright capabilities.
4. **Kagent / MCP** is a separate entry path into Tool Agent; Platform Orchestrator does not replace it.

## Envelope shapes (logical)

### TaskRequest

```yaml
task_id: string          # platform-generated ULID
correlation_id: string   # client / parent workflow id
agent_id: string         # support-agent (orchestrator) | tool-agent | db-agent | ui-test-agent
capability: string       # e.g. tools.grafana.query
op: discover|plan|execute|stream|status|cancel|feedback
idempotency_key: string  # required for execute
budget:
  max_latency_ms: int
  max_cost_units: number
  max_fanout: int
auth:
  service_token_ref: string   # opaque; never pass raw secrets to LLM
payload: object               # agent-specific; redacted before LLM
```

### TaskResult

```yaml
task_id: string
status: accepted|running|succeeded|failed|cancelled|timed_out
agent_id: string
evidence:
  - kind: string
    ref: string           # opaque docs_ref / artifact_ref
    provenance: string
error:
  code: string
  message: string         # redacted
  retryable: bool
metrics:
  latency_ms: int
  cost_units: number
```

### AgentCard

```yaml
agent_id: string
display_name: string
base_url: string
capabilities:
  - id: string
    ops: [discover, plan, execute, stream, status]
    preferred: bool       # true for tool-agent overlaps
health:
  path: /health
auth:
  scheme: bearer|none|header
  header: string          # e.g. X-Agent-Caller for db-agent
limits:
  multi_replica_status: bool  # false for ui-test-agent
```

### FeedbackEvent

```yaml
task_id: string
run_ref: string
rating: pass|fail|partial|unsafe
labels: [string]
notes: string             # redacted
proposed_change:
  kind: prompt|policy|playbook
  candidate_ref: string
```

## Security

| Rule | Requirement |
|------|-------------|
| Service identity | Every A2A call uses a service token / allowlisted caller header |
| Registry allowlist | Orchestrator may only call agents listed in `registry/agents.yaml` |
| Secrets | `secret_ref` only in control plane; never in Temporal payloads or LLM prompts |
| Redaction | Adapter outputs pass redactor before analysis / storage of free text |
| Fan-out | Router enforces `max_fanout` and per-agent concurrency |

## Idempotency

- `execute` requires `idempotency_key`.
- Platform RunStore is source of truth for platform-level retries.
- UI Test in-memory status is **not** an idempotency store; adapters must not assume HA status across replicas.

## Budget / cost controls

Every plan includes budgets. Router rejects or truncates DAGs that exceed:

- `max_fanout`
- `max_latency_ms` (wall clock for the platform task)
- `max_cost_units` (LLM + tool estimated cost)

## Explicit non-goals for specialist agents

Specialists will **not** be changed in the structure / parallel-build phases to add discover/cancel/feedback. Those remain platform responsibilities until a future, separately approved specialist API revision.
