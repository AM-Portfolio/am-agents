# Migration map — legacy platform → support-agent/

**Rule:** Map and run in parallel. Relocate or delete only after [production gates](../docs/architecture/production-gates.md).

**Status legend:** ✅ implemented in `support-agent/` · 📄 docs-only / future-gated · ⛔ external (legacy/specialist unchanged)

Last audited: 2026-07-18

## Specialists (never migrate into agent-platform; never delete in decommission)

| Current path | Target | Status | Notes |
|--------------|--------|--------|-------|
| `tool-agent/` | stay | ⛔ | Preferred executor; HTTP + MCP — adapters only at `src/am_support_agent/adapters/` (`ToolAgentAdapter`) |
| `db-agent/` | stay | ⛔ | Legacy; `DbAgentAdapter` + `legacy.db-agent` gate |
| `ui-test-agent/` | stay | ⛔ | Browser specialist; `UiTestAgentAdapter` synthesizes plan / polls status |

## Orchestration path (legacy → replacement)

| Current path | Replacement target | Status | Exact path |
|--------------|--------------------|--------|------------|
| `gateway/` | `support-agent/gateway/` | ✅ | `src/am_support_agent/gateway/app.py` (port **8091**, service `support-agent-gateway`) |
| `platform_worker/` | `support-agent/orchestrator/` | ✅ | `src/am_support_agent/orchestrator/` + `worker_main.py` (queue **`support-agent-v2`**) |
| `platform_worker/.../workflows/alert_incident.py` | `orchestrator/workflows/alert_incident` | ✅ | `src/am_support_agent/orchestrator/workflows/alert_incident.py` — Temporal name `AlertIncidentWorkflow`; HITL signals identical; acceptance gate + finalize; side effects behind `SUPPORT_AGENT_INCIDENT_PARITY` |
| `platform_worker/.../workflows/spt_run.py` | `orchestrator/workflows/spt_run` | ✅ | `src/am_support_agent/orchestrator/workflows/spt_run.py` — Temporal name `SptRunWorkflow`; catalog resolve read-only; execute path behind `SUPPORT_AGENT_SPT_PARITY` (sandbox fail-closed) |
| `platform_worker/.../activities/*` | `orchestrator/activities/*` | ✅ | `activities/a2a.py` (live), `activities/incident.py` (parity gate + validate/plan/episode), `activities/spt.py` (parity + capability spt.*) |
| Temporal signals `approve`, `alert.resolved`, `alert.refired` | `orchestrator/hitl/` | ✅ | `src/am_support_agent/orchestrator/hitl/__init__.py` — same signal name strings |
| A2A DAG workflow | `orchestrator/workflows/a2a_run` | ✅ | `workflows/a2a_run.py` → `SupportA2AWorkflow` |

## Shared libraries (seed, not delete)

| Current path | Replacement use | Status | Strategy |
|--------------|-----------------|--------|----------|
| `libs/platform-ports/` | Seed for contracts / ports | 📄 | Prefer depend via future composition root; A2A schemas live in `src/am_support_agent/contracts/` (complement, do not fork incident schemas) |
| `libs/platform-adapters/` | Seed for RunStore, MinIO, LLM, tickets, tool-agent observe | 📄 | **Do not** wire legacy `PostgresRunStore`/`agent_runs` for A2A. DocStore prefix helpers: `adapters/storage.py`. LLM gate: `adapters/llm.py` |
| `libs/agent-common/` | OTel / HTTP helpers | 📄 | Keep shared; support-agent ships local metrics in `observability/` |

## Catalog and prompts

| Current path | Replacement use | Status | Exact path |
|--------------|-----------------|--------|------------|
| `catalog/prompts/` | `intelligence/prompts` + procedural memory | ✅ read-only | `src/am_support_agent/intelligence/catalog.py` (`CatalogReader`); env `SUPPORT_AGENT_CATALOG_ROOT` |
| `catalog/verify/` | `intelligence/verification` | ✅ read-only | same `CatalogReader.list_verify()` |
| `catalog/spt/` | SPT workflow targets | ✅ read-only | `CatalogReader.list_spt()` + SPT activity `resolve_spt_catalog` |
| Gateway catalog API | — | ✅ | `GET /v2/catalog` |

## Capability ownership (frozen)

| Concern | Status | Exact path |
|---------|--------|------------|
| Neutral capability IDs + ownership matrix | ✅ | [`docs/capability-ownership.md`](docs/capability-ownership.md) |
| Capability DTOs (work-item, chat, mail, document, observe, spt) | ✅ | `src/am_support_agent/contracts/capabilities.py` |
| Incident gate DTOs (`IncidentContext`, `IncidentValidation`, episode/feedback) | ✅ | `src/am_support_agent/contracts/incident.py` |
| Tool-agent generic plugins + vendor adapters | ✅ | `tool-agent/tools/{work_item,chat,mail,document,directory,observe,spt}/` (+ `docs/CAPABILITY_PLUGINS.md`); gated via `TOOL_AGENT_CAPABILITY_PLUGINS` |
| Post-assignment acceptance gate wiring | ✅ | `intelligence/context.py` (`IncidentValidator`) + `activities/incident.py` behind `SUPPORT_AGENT_INCIDENT_PARITY` |

## Integrations

| Current path | Replacement use | Status | Exact path |
|--------------|-----------------|--------|------------|
| `k8s/kagent/` | `integrations/kagent` (optional) | ✅ docs + status | `src/am_support_agent/integrations/kagent.py`; `GET /v2/integrations` — **not** in orchestrator binary |
| Tool Agent MCP bridge (`:8085`) | Documented integration | ✅ | Env `TOOL_AGENT_MCP_URL`; platform HTTP adapters remain separate |
| GrowthBook route flag | Runtime legacy/new selection | ✅ | `parity/growthbook_flags.py` + `GROWTHBOOK_ROUTE_FEATURE_KEY`; unavailable service fails closed to legacy |
| Composition root | `ports/` + `composition.build_runtime()` | ✅ | Capability/LLM/docs/catalog/prompts/semantic/episodes/feedback/security stubs; fail-closed with `SUPPORT_AGENT_REQUIRE_LIVE_ADAPTERS` |
| DocStore client | memory / optional MinIO | ✅ | Prefixed `support-agent-v2/` via composition DocumentStore |
| LLM port | gated + fake | ✅ | Live provider still gated; FakeLlmClient in test mode |

## Deploy / CI gaps

| Current | Gap | Replacement | Status |
|---------|-----|-------------|--------|
| Gateway / worker Docker+Helm | Central + local | `support-agent/helm/` (universal-chart + companion worker) · `deploy/helm/` (local PVC scaffold) | ✅ |
| Dockerfile | — | `support-agent/Dockerfile` (+ `deploy/docker/README.md`) | ✅ |
| Helm | — | Central values under `helm/`; standalone under `deploy/helm/` | ✅ |
| CI | — | `.github/workflows/support-agent.yml` → test + helm + `central-build-publish` | ✅ |
| Specialist Helm | Exists under each agent | Unchanged | ⛔ |

## Data stores

| Concern | Current | Parallel rule | Status | Exact path |
|---------|---------|---------------|--------|------------|
| RunStore (A2A) | memory / sqlite / dedicated Postgres | Distinct from legacy `agent_runs` | ✅ | `stores/run_store.py`, `stores/postgres.py`, schema `support_agent.task_runs` (`stores/schema.py`). Env `SUPPORT_AGENT_RUNSTORE=memory\|sqlite\|postgres` + `SUPPORT_AGENT_DATABASE_URL` |
| Workflow ledger (incident/SPT) | memory / sqlite | Distinct from A2A task_runs and legacy agent_runs | ✅ | `stores/workflow_ledger.py` + gateway `/v2/workflows/*` + `/v2/handoff`. Postgres backend 📄 |
| RunStore (legacy) | Postgres via `platform-adapters` | **Never** overloaded for A2A | 📄 gate | Documented in `docs/run-store.md`; `legacy_postgres_runstore_compatible() == False` |
| DocStore | MinIO (+ GDrive failover) | Distinct bucket/prefix for v2 | ✅ | `adapters/storage.py` + `adapters/documents.py` via composition; prefix `support-agent-v2/` |
| Qdrant | Agent-local only | Do not claim platform ownership | 📄 | See `memory/README.md` |
| Temporal | Queue `agent-platform` | Use `support-agent-v2` until cutover | ✅ | Worker refuses `agent-platform` |

## Learning

| Concern | Status | Exact path |
|---------|--------|------------|
| Feedback ingest + promotion gate | ✅ hard gate (no auto-promote) | `src/am_support_agent/learning/__init__.py` |
| Episode store (in-memory) | ✅ | `stores/episodes.py` + `persist_episode` / `EpisodeRetriever` |
| Offline eval / candidates store | 📄 | Folder intent in `learning/README.md` |
| Context / validator / planner | ✅ | `intelligence/context.py` |

## Deletion eligibility (legacy only)

Eligible for Gate E inventory **after** production soak:

- `gateway/` (legacy)
- `platform_worker/` (legacy)
- Legacy-only deploy manifests / CI jobs that point solely at those packages
- Legacy-only Temporal queue consumers after drain

**Never** on the deletion list:

- `tool-agent/`, `db-agent/`, `ui-test-agent/`
- `catalog/` (until ownership explicitly transferred)
- `libs/platform-ports`, `libs/platform-adapters`, `libs/agent-common` (unless replaced with published packages and all consumers migrated)
- `k8s/kagent/` (unless separately owned migration)

Template: [`DECOMMISSION.md`](DECOMMISSION.md)

## README / docs inventory updates

| Doc | Change | Status |
|-----|--------|--------|
| Root `README.md` | Tool active, DB legacy, support-agent parallel module | ✅ |
| `docs/MONOREPO_PLAN.md` | Historical; superseded for layout by architecture docs | 📄 historical |
| `docs/agent-platform/` (Temporal ports SoT) | Keep; link from support-agent README | ✅ (path was formerly referred to as `docs/support-agent/`) |
| `docs/architecture/*` | Agent platform / A2A / gates | ✅ |
| `support-agent/docs/run-store.md` | A2A backends + Postgres schema | ✅ |
| `support-agent/docs/parity.md` | Shadow thresholds + canary modes / rollback | ✅ |
| `support-agent/docs/capability-ownership.md` | Neutral capabilities + ownership freeze | ✅ |

## Externally gated (cannot finish inside support-agent alone)

| Item | Why gated | Unblock |
|------|-----------|---------|
| Live vendor ticket/chat/observe (non-fake) | Needs tool-agent capability plugins + vendor credentials | Enable `TOOL_AGENT_CAPABILITY_PLUGINS` + `SUPPORT_AGENT_INCIDENT_PARITY` with live `CapabilityClient` |
| Full SPT child Temporal fan-out | Capability path wired; multi-child Temporal fan-out still thin | `SUPPORT_AGENT_SPT_PARITY=true` + live `spt.*` plugins; deepen child workflows as needed |
| MinIO DocStore client | Shared adapters package; prefix boundary only here | Wired via `composition.build_runtime()` DocumentStore (memory default; MinIO when configured) |
| Live LLM completions | Redaction + LlmPort composition | `SUPPORT_AGENT_LLM_ENABLED` + ports root |
| Production cutover / legacy deletion | Gates A–E | [production-gates.md](../docs/architecture/production-gates.md) |
| Specialist API gaps (native cancel/stream) | Adapters already compensate | Leave specialists unchanged |
