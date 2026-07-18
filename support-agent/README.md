# support-agent/

**Canonical agent name:** `support-agent` (Support Agent)  
**Path:** `am-agents/support-agent/` · package `am_support_agent`

**Hard rules:** Build alongside legacy. Prove in production. Delete legacy only after [production gates](../docs/architecture/production-gates.md) + explicit approval.

## Implementation status

**Phases 1–3 (parallel module) in place** — A2A gateway/worker, HITL scaffolds,
catalog reader, dedicated A2A Postgres schema, Helm/CI. Full AlertIncident/SPT
side effects remain **gated** until ports composition (see
[MIGRATION_MAP.md](MIGRATION_MAP.md)). Legacy untouched.

```bash
cd support-agent
pip install -e ".[dev,temporal]"
# optional: pip install -e ".[postgres]"
pytest -q
# gateway v2 (port 8091 — distinct from legacy 8090)
set SUPPORT_AGENT_API_TOKEN=dev-token
am-support-agent-gateway
```

- **Identity:** `support-agent` / display `Support Agent`
- **APIs:** health/readiness/metrics, A2A, planning, execution, task status,
  catalog summary, integrations status, side-effect-free shadow comparison,
  and optional Temporal workflow start
- **Deploy scaffold:** `Dockerfile`, `deploy/helm/` (optional SQLite PVC +
  worker Temporal env), `deploy/docker/`, `deploy/ci/`, `.env.example`
- **Does not** modify or import legacy `gateway/` / `platform_worker/`
- **Does not** change tool/db/ui-test agents
- Temporal worker: `am-support-agent-worker` (queue `support-agent-v2` only)
  registers `SupportA2AWorkflow`, gated `AlertIncidentWorkflow` + `SptRunWorkflow`
- Optional workflow start: `POST /v2/workflows/a2a` when `SUPPORT_AGENT_TEMPORAL_ENABLED=true`
- Task ledger: memory (default), SQLite, or dedicated Postgres schema
  `support_agent.task_runs` — **not** legacy `agent_runs`
- Shadow: `POST /v2/shadow` allows `discover`/`plan` only; threshold `1.0`
  after ignored volatile keys — see [docs/parity.md](docs/parity.md)
- Cancel/feedback: store records even when the target task is missing
  (`payload.target_task_id`); feedback appends without clobbering prior result
- CI: `.github/workflows/support-agent.yml` — pytest, compileall, Helm
  lint/render (worker + PVC), Docker build

## Observability

The gateway publishes Prometheus text format at `GET /metrics`. Kubernetes
scrapes that endpoint directly; traces use OTLP/HTTP to
`otel-collector.monitoring.svc.cluster.local:4318/v1/traces`, which forwards to
Tempo. The flow is:

`FastAPI inbound span → support_agent.task span → W3C traceparent on specialist HTTPX request`

Temporal client/worker tracing uses Temporal's OpenTelemetry interceptor, so
workflow and activity spans are created by the SDK without adding
nondeterministic calls to workflow code.

Tracing configuration:

- `SUPPORT_AGENT_TRACING_ENABLED` — explicit on/off switch (default on when an
  endpoint exists)
- `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` — OTLP/HTTP traces URL; unset disables
  tracing
- `OTEL_SERVICE_NAME`, `OTEL_SERVICE_NAMESPACE`, `SUPPORT_AGENT_VERSION`,
  `DEPLOYMENT_ENVIRONMENT` — resource identity
- `OTEL_TRACES_SAMPLER_ARG` (or `TRACING_SAMPLING_PROBABILITY`) — parent-based
  trace-id sampling ratio, clamped to 0–1

OpenTelemetry is failure-optional: missing packages, a disabled SDK, or an
unset endpoint leaves request handling operational. Spans contain only
allowlisted operational attributes (`agent.id`, specialist agent, operation,
capability, task/correlation IDs, domain, automation mode, and status). They
never contain payloads, auth/idempotency values, response bodies, or secrets.

Technical metrics:

- `support_agent_a2a_requests_total`
- `support_agent_adapter_latency_seconds`
- `support_agent_errors_total`, `support_agent_timeouts_total`
- `support_agent_cancelled_total`, `support_agent_idempotency_hits_total`
- `support_agent_in_flight_tasks`, `support_agent_run_store_healthy`
- `support_agent_shadow_parity_total`

Business metrics:

- `support_agent_business_requests_total`
- `support_agent_resolution_outcomes_total`
- `support_agent_automation_total`
- `support_agent_hitl_total`

Clients may set `business_domain` to one of `technical`, `billing`, `product`,
`internal`, `external`, or `unknown` (default). `requires_human` is boolean.
These are strict schema fields; payload/free-text classification is never used
as a metric label.

Example PromQL:

```promql
sum by (agent, status) (rate(support_agent_a2a_requests_total[5m]))
histogram_quantile(0.95, sum by (le, agent) (rate(support_agent_adapter_latency_seconds_bucket[5m])))
sum by (domain, outcome) (rate(support_agent_resolution_outcomes_total[1h]))
sum(rate(support_agent_shadow_parity_total{result="pass"}[1h]))
/
sum(rate(support_agent_shadow_parity_total[1h]))
```


## Purpose

Replace the orchestration surface of today’s `gateway/` + `platform_worker/` with **support-agent** — a full Agent Platform that:

- Speaks a stable **A2A** contract
- Calls **existing** Tool / DB / UI Test agents via adapters (no specialist code changes)
- Owns planning, routing, analysis, verification, HITL, memory mapping, and gated learning
- Deploys in parallel with distinct identity until cutover

Specialist agents (`tool-agent/`, `db-agent/`, `ui-test-agent/`) are **not** part of this module and are **never** decommissioned by platform deletion.

## Target tree (complete module — implement only after code authorization)

```text
support-agent/
├── README.md                          # this file
├── MIGRATION_MAP.md                   # current path → target path
├── gateway/                           # L2 HTTP API + auth + Temporal client
├── orchestrator/
│   ├── planner/
│   ├── router/
│   ├── workflows/                     # AlertIncident, SPT, generic A2A DAG
│   ├── activities/
│   └── hitl/                          # approve / alert.resolved / alert.refired
├── contracts/
│   ├── a2a/                           # task/result/stream/feedback schemas
│   ├── capabilities/                  # agent cards
│   ├── evidence/
│   └── feedback/
├── registry/
│   └── agents.yaml                    # endpoints + capabilities + preference
├── adapters/
│   ├── tool_agent/
│   ├── db_agent/
│   ├── ui_test_agent/
│   ├── storage/                       # RunStore / DocStore facades
│   └── llm/
├── intelligence/
│   ├── analysis/
│   ├── verification/
│   ├── prompts/                       # may consume catalog/ until cutover
│   └── policies/
├── memory/
│   ├── episodic/                      # → Postgres RunStore
│   ├── semantic/                      # ownership TBD vs agent-local Qdrant
│   ├── procedural/                    # → catalog prompts/verify/spt
│   └── artifacts/                     # → MinIO
├── learning/
│   ├── feedback/
│   ├── evaluation/
│   ├── candidates/
│   └── promotion/                     # gated; never auto-live
├── runtime/
│   ├── auth/
│   ├── budgets/
│   ├── idempotency/
│   └── resilience/
├── observability/
├── tests/
│   ├── contract/
│   ├── integration/
│   ├── e2e/
│   ├── parity/                        # vs legacy gateway/worker
│   └── load/
└── deploy/
    ├── docker/
    ├── helm/
    └── ci/
```

## Phase 0 deliverables in this folder

| File | Role |
|------|------|
| [README.md](README.md) | Module boundary + tree |
| [MIGRATION_MAP.md](MIGRATION_MAP.md) | Legacy → replacement mapping |
| [contracts/README.md](contracts/README.md) | Contract package index |
| [contracts/a2a.md](contracts/a2a.md) | A2A schema notes |
| [contracts/capabilities.md](contracts/capabilities.md) | Agent cards + routing |
| [registry/agents.md](registry/agents.md) | Registry design (YAML later) |
| [adapters/README.md](adapters/README.md) | Adapter responsibilities |
| [memory/README.md](memory/README.md) | Store mapping |
| [learning/README.md](learning/README.md) | Gated learning |
| [DECOMMISSION.md](DECOMMISSION.md) | Deletion inventory template |

## Architecture docs

- [docs/architecture/agent-platform.md](../docs/architecture/agent-platform.md)
- [docs/architecture/a2a-protocol.md](../docs/architecture/a2a-protocol.md)
- [docs/architecture/execution-flow.md](../docs/architecture/execution-flow.md)
- [docs/architecture/production-gates.md](../docs/architecture/production-gates.md)

## Relationship to existing Temporal design SoT

Keep [docs/agent-platform/](../docs/agent-platform/) as the historical design package for ports / RunStore / AlertIncident. This folder documents the **parallel A2A replacement** and production cutover rules. Do not delete the old design docs when building the new module.

## Import / coupling rule (when code is authorized)

- New module must not take a **runtime import dependency** on legacy `gateway` or `platform_worker` packages.
- Shared contracts may come from `libs/platform-ports` or from new `support-agent/contracts` with a documented provenance in `MIGRATION_MAP.md`.
- Behavior may be copied and reviewed; do not couple the replacement to code scheduled for retirement.
