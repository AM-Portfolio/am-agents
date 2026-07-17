# Agent platform — phase checklist

Parent: [DESIGN.md](DESIGN.md) · Layout: [FOLDER_STRUCTURE.md](FOLDER_STRUCTURE.md) · Index: [README.md](README.md)  
**Docs home:** `am-agents/docs/agent-platform/` only

**Rules locked across phases:** Temporal workflows → ports only · opaque refs · no secrets/env to LLM ([ADR-002](decisions/ADR-002-privacy-sandbox-secrets.md)) · extractable `libs/platform-ports` ([ADR-003](decisions/ADR-003-extractable-sdk.md)) · SPT: catalog + selectors only, never default-all, zero service names in code (ADR-004)

---

## Phase 0a — Design docs

- [x] Single folder `docs/agent-platform/` (no duplicate `design/` + `diagrams/` split)
- [x] `DESIGN.md` + `PHASES.md` + `FOLDER_STRUCTURE.md`
- [x] `sheets/*.mmd` + `agent-platform.drawio`
- [x] `docs/README.md` index; enterprise diagrams stay under `docs/diagrams/`
- [x] [ADR-001](decisions/ADR-001-temporal-agent-ports.md) Temporal → ports
- [x] [ADR-002](decisions/ADR-002-privacy-sandbox-secrets.md) privacy / SecretBroker / ToolSandbox / Redactor / LlmPort
- [x] [ADR-003](decisions/ADR-003-extractable-sdk.md) extractable `libs/platform-ports` (reuse by other agents)
- [ ] **ADR-004** SPT catalog + selectors + partial-failure + `prep_ref` + runaway guards
- [ ] **User confirmation** — approve design (rev 1.3 + ADR-002/003/004) before Phase 0b code

---

## Phase 0b — Ports (blocked on confirmation)

- [ ] **`libs/platform-ports`** (`am_platform_ports`) — Protocols + schemas + fakes + contract tests
- [ ] Core ports: Triage, TicketStore, Notifier, Directory, Policy, PromptRegistry, SecretBroker, ToolSandbox, Redactor, LlmPort
- [ ] SPT schemas/ports (stubs OK until P3 adapters): `TargetCatalog`, `TargetResolver`, `LoadPolicy`, `LoadTestRunner`, `DataPrep`, `ObservabilityPort`
- [ ] SPT request/result schemas: `SptDemandRequest` (`ids`/`tags` only; empty selector = fatal), `ChildRunResult`, `SptRunSummary`, `failure_mode: continue | fail_fast`
- [ ] `libs/agent-common` + `libs/platform-adapters` stubs (SecretBroker / Sandbox / Llm / Redactor)
- [ ] `catalog/prompts/` skeleton
- [ ] Prove reuse: another agent path imports `TicketStore` (or fake) from `am_platform_ports` only

**Done when:** CI green on ports package; no vendor SDKs inside `am_platform_ports`.

---

## Phase 1 — AlertIncident MVP

- [ ] Temporal lab + `platform_worker`
- [ ] `AlertIncidentWorkflow` + Alert Ops thin edge (`StartWorkflow` / `Signal` only)
- [ ] OpenProject `TicketStore` + `Directory`; Cliq `Notifier` (follow-up cards only)
- [ ] Flap / silence / race state machine
- [ ] PromptRegistry from catalog (no prompt bodies in Python)
- [ ] Lab smoke: FIRING → ticket + Cliq ≤ 60s; RESOLVED

---

## Phase 2 — Docs + infra

- [ ] DocStore MinIO primary + `FailoverDocStore` → GDrive
- [ ] InfraOps + `Approve` signal (allowlisted)
- [ ] `work_done` on `agent.resolved`

---

## Phase 3 — SPT (lab)

### Catalog + adapters

- [ ] File `TargetCatalog` over `catalog/spt/` (services + flows); JSON Schema validate
- [ ] `LoadTestRunner` via ToolSandbox (e.g. k6); secrets only via SecretBroker
- [ ] `DataPrep.ensure_dataset(prep_ref)` — **once per distinct `prep_ref` per parent run** (dedupe)
- [ ] Lab catalog: ≥3 services (2 share one `prep_ref`, 1 without) + 1 flow
- [ ] Zero service/repo names in `platform_worker/` or `libs/platform-ports/` (catalog data only)

### Workflow

- [ ] `SptRunWorkflow` resolve → policy → fan-out children (bounded parallelism)
- [ ] Default `failure_mode: continue`; optional `fail_fast`
- [ ] Aggregate `SptRunSummary` (`succeeded` / `partial` / `failed`); `spt.completed` notify with counts (never false all-green on partial)
- [ ] Observe via `query_ref` (Grafana HTTP); aggregate report → DocStore → Cliq

### Acceptance (lab)

- [ ] Smoke: request ≥2 targets, `parallelism: 2`
- [ ] Partial drill: one child fails, sibling succeeds → parent `overall_status: partial` + correct counts
- [ ] Parent summary + `docs_ref` within `max(child durations) + 5m`

### Growth / CI

- [ ] CI growth test: add fixture YAML → TargetSet grows; worker/ports paths unchanged
- [ ] No-hardcode lint: no real service/repo ids in worker/ports source
- [ ] Manifest schema check on `catalog/spt/services/*.yaml`

**Done when:** lab fan-out smoke + `spt-growth` CI green.

---

## Phase 4 — Jira / Mail / Calendar

- [ ] Jira `TicketStore` adapter (same workflows; env swap)
- [ ] Zoho Mail + Calendar ports/adapters

---

## Phase 5 — Gateway / handoff / prod SPT

- [ ] L2 chat gateway (Start / Signal / status + auth)
- [ ] `HandoffPort` max depth 1
- [ ] Policy-gated prod SPT: catalog `enabled: false` default; Approve + change window; mandatory observe + doc
- [ ] Runaway guards live: `SPT_MAX_TARGETS_PER_RUN`, `SPT_MAX_PARALLEL`, `SPT_MAX_CONCURRENT_RUNS`; empty selector fatal; `all: true` only lab + Approve + under max
- [ ] Audit: resolve logs selector hash + `expanded_count`; alert if expansion > max

### Soak checklist (ship score 10)

- [ ] Catalog ≥ 30 real service entries (or all P0 tier)
- [ ] ≥ 2 weeks lab demand traffic
- [ ] Zero accidental all-target expands
- [ ] ≥ 1 intentional partial run with correct Cliq counts
- [ ] Growth CI green on every PR touching worker/ports
- [ ] Sandbox time/RPS kill proven under fault injection

---

## Confirmation gate

```text
Status: AWAITING CONFIRMATION
Approved by: —
Approved at: —
Approved design revision: 1.3 (ADR-002 + ADR-003 + ADR-004)
Next step after approve: Phase 0b — libs/platform-ports first
```

Reply **approve design** (or request changes) before Protocol/adapter implementation.
