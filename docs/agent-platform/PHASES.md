# Agent platform — phase checklist

Parent: [DESIGN.md](DESIGN.md) · Layout: [FOLDER_STRUCTURE.md](FOLDER_STRUCTURE.md) · Index: [README.md](README.md)  
**Docs home:** `am-agents/docs/agent-platform/` only

**Rules locked across phases:** Temporal → ports only · opaque refs · no secrets to LLM ([ADR-002](decisions/ADR-002-privacy-sandbox-secrets.md)) · extractable SDK ([ADR-003](decisions/ADR-003-extractable-sdk.md)) · **RunStore intake + step updates** ([ADR-005](decisions/ADR-005-runstore-verify.md)) · SPT catalog + selectors only (ADR-004) · verify gate A blocks done until pass

---

## Phase 0a — Design docs

- [x] Single folder `docs/agent-platform/` (no duplicate `design/` + `diagrams/` split)
- [x] `DESIGN.md` + `PHASES.md` + `FOLDER_STRUCTURE.md`
- [x] `sheets/*.mmd` + `agent-platform.drawio` (incl. RunStore + Verify)
- [x] `docs/README.md` index; enterprise diagrams stay under `docs/diagrams/`
- [x] [ADR-001](decisions/ADR-001-temporal-agent-ports.md) Temporal → ports
- [x] [ADR-002](decisions/ADR-002-privacy-sandbox-secrets.md) privacy / SecretBroker / ToolSandbox / Redactor / LlmPort
- [x] [ADR-003](decisions/ADR-003-extractable-sdk.md) extractable `libs/platform-ports`
- [x] [ADR-005](decisions/ADR-005-runstore-verify.md) RunStore + post-fix verify gate A
- [x] [ADR-004](decisions/ADR-004-spt-catalog-selectors.md) SPT catalog + selectors + partial-failure + `prep_ref` + runaway guards
- [x] **User confirmation** — development started (rev 1.4)

---

## Phase 0b — Ports

- [x] **`libs/platform-ports`** (`am_platform_ports`) — Protocols + schemas + fakes + contract tests
- [x] Core ports: Triage, TicketStore, Notifier, Directory, Policy, PromptRegistry, SecretBroker, ToolSandbox, Redactor, LlmPort
- [x] **`RunStore`** + schemas: `create_run`, `upsert_step`, `claim_pending`, `heartbeat`, `complete`
- [x] SPT schemas/ports (stubs): `TargetCatalog`, `TargetResolver`, `LoadPolicy`, `LoadTestRunner`, `DataPrep`, `ObservabilityPort`
- [x] SPT request/result schemas: `SptDemandRequest`, `ChildRunResult`, `SptRunSummary`, `failure_mode`
- [x] `libs/agent-common` + `libs/platform-adapters` stubs (`build_*` → fakes)
- [x] `catalog/prompts/` + `catalog/verify/` skeletons
- [x] Prove reuse: contract test imports `TicketStore` from `am_platform_ports` only

**Done when:** CI green on ports package; no vendor SDKs inside `am_platform_ports`. — **local pytest: 6 passed**

**Note:** Phase 0b does **not** require Temporal — ports, fakes, and contract tests run without a cluster.

---

## Prerequisites — before Phase 1

**Status today:** Temporal **installed** on VPS kind cluster `kind-am-preprod` (namespace `temporal`).

| Step | Owner | Status |
|------|-------|--------|
| Temporal on existing infra Postgres | am-infra `k8s/temporal/` | **Done** — no Cassandra/ES; DBs `temporal` + `temporal_visibility` on `postgresql.infra` |
| Frontend reachable in-cluster | — | `temporal-frontend.temporal.svc.cluster.local:7233` |
| UI | — | `kubectl -n temporal port-forward svc/temporal-web 8080:8080` |
| Worker registers | am-agents | Pending Phase 1 `platform_worker` |
| Alert Ops client stub | am-obs-platform | Pending Phase 1 `temporal_client.py` |

Kubeconfig: `VPS/VPS/kubeconfig.vps` (context `kind-am-preprod`).

Phase 0b can proceed in parallel (ports need no Temporal). Phase 1 workflows need the frontend above.

---

## Phase 1 — AlertIncident MVP

- [x] **Prerequisite:** Temporal lab on VPS kind (`temporal` ns, existing Postgres) + `default` namespace registered
- [x] `platform_worker` registers with Temporal (`localhost:7233` via port-forward / in-cluster frontend)
- [x] `AlertIncidentWorkflow` + signals `alert.resolved` / `alert.refired`
- [x] Alert Ops thin edge (`relay/temporal_client.py`): FIRING→Start / re-FIRING→refired / RESOLVED→Signal
- [x] **`RunStore.create_run` on Start** (kind=`alert_incident`); upsert steps triage / ticket / notify (in-memory fake)
- [x] Cliq `Notifier` adapter (`ALERT_NOTIFY_PROVIDER=cliq` → opslab via `ZOHO_CLIQ_LAB_WEBHOOK_URL` from am-obs-platform `.env`)
- [x] OpenProject `TicketStore` + `Directory` (`TICKET_PROVIDER=openproject`, `DIRECTORY_PROVIDER=openproject`)
- [x] Flap / silence / race basics: refired signal (no 2nd WF); silence = no resolve signal; first closer via `alert.resolved`
- [x] PromptRegistry from catalog key `triage.default` (fake registry; YAML under `catalog/prompts/`)
- [x] Lab smoke: Alert Ops edge Start→worker→Cliq; RESOLVED signal → passed

**Smoke:** Cliq `alert-e811692a08`; Alert Ops edge `alert-incident-AM-20260717-873067` started+resolved (`scripts/smoke_temporal_edge.py`).
Enable in relay: `TEMPORAL_AGENT_ENABLED=1` + `TEMPORAL_HOST=localhost:7233` (see `.env.example`).
OP: `OPENPROJECT_URL` + `OPENPROJECT_API_TOKEN` (plaintext) + `OPENPROJECT_PROJECT_ID=3` (ASRAX FinTech, type Task=1); default assignee user `5` (munish — project member). Live: `op:wp:372`.

---

## Phase 2 — Docs + infra + verify

- [x] DocStore MinIO primary + `FailoverDocStore` → GDrive (GDrive stub; failover wrapper live)
- [x] InfraOps + `Approve` signal (allowlisted `lab.mark_fixed` via ToolSandbox; Gate A `approve`)
- [x] **Postgres RunStore adapter** (`RUN_STORE_PROVIDER=postgres`, DB `agent_platform`)
- [x] After resolve → **`kind=verify` run** + pending steps from `catalog/verify/` (`check_ref`)
- [x] Claim loop (activity): pull `pending` → lease → ObservabilityPort → complete + DocStore result
- [x] **Gate A:** block done until verify `passed` or human `approve` signal
- [x] Lab smoke: verify `passed` → done (`closer=verify.passed`); verify `failed` → `needs_human` → `approve` → done

---

## Phase 3 — SPT (lab)

### Catalog + adapters

- [x] File `TargetCatalog` over `catalog/spt/` (services + flows); JSON Schema validate (`target.schema.json`)
- [x] `LoadTestRunner` via ToolSandbox (`lab.k6`); secrets refs only (no plaintext URLs in code)
- [x] `DataPrep.ensure_dataset(prep_ref)` — **once per distinct `prep_ref` per parent run** (dedupe)
- [x] Lab catalog: ≥3 services (2 share `prep.shared-lab`, 1 without) + 1 flow
- [x] Zero service/repo names in `platform_worker/` or `libs/platform-ports/` (catalog data only)

### Workflow + RunStore

- [x] **`RunStore.create_run` on SPT demand** (kind=`spt`); child runs + step updates
- [x] `SptRunWorkflow` resolve → policy → fan-out children (bounded parallelism)
- [x] Default `failure_mode: continue`; optional `fail_fast`
- [x] Aggregate `SptRunSummary`; `spt.completed` notify with counts
- [x] Observe via `query_ref`; aggregate report → DocStore → Cliq

### Acceptance (lab)

- [x] Smoke: request ≥2 targets, `parallelism: 2`; RunStore shows parent + children statuses
- [x] Partial drill: one child fails, sibling succeeds → parent `partial` + correct counts
- [x] Parent summary + `docs_ref` (MinIO) on finalize

### Growth / CI

- [x] CI growth test: add fixture YAML → TargetSet grows; worker/ports paths unchanged
- [x] No-hardcode lint: catalog ids only under `catalog/spt/` (worker/ports free of tgt-* hardcodes)
- [x] Manifest schema check on `catalog/spt/services/*.yaml`

**Done when:** lab fan-out smoke + `spt-growth` CI green. — **lab acceptance green**

---

## Phase 4 — Jira / Mail / Calendar

- [x] Jira `TicketStore` adapter (same workflows; `TICKET_PROVIDER=jira`)
- [x] Zoho Mail + Calendar ports/adapters (`MAIL_PROVIDER` / `CALENDAR_PROVIDER` = `fake|zoho`)

---

## Phase 5 — Gateway / handoff / prod SPT

- [x] L2 chat gateway (Start / Signal / status + auth) — gateway Start also **create_run**
- [x] `HandoffPort` max depth 1
- [x] Policy-gated prod SPT: catalog `enabled: false` default; Approve + change window; observe + doc via existing finalize path
- [x] Runaway guards live: `SPT_MAX_TARGETS_PER_RUN`, `SPT_MAX_PARALLEL`, `SPT_MAX_CONCURRENT_RUNS`; empty selector fatal; `all: true` only lab + Approve + under max
- [x] Audit: resolve logs selector hash + `expanded_count`; alert if expansion > max

### Soak checklist (ship score 10)

- [ ] Catalog ≥ 30 real service entries (or all P0 tier)
- [ ] ≥ 2 weeks lab demand traffic
- [ ] Zero accidental all-target expands
- [ ] ≥ 1 intentional partial run with correct Cliq counts
- [ ] Growth CI green on every PR touching worker/ports
- [ ] Sandbox time/RPS kill proven under fault injection
- [ ] Verify gate A exercised in lab (≥1 fail + ≥1 pass path)

---

## Confirmation gate

```text
Status: APPROVED — development started
Approved by: user
Approved at: 2026-07-18
Approved design revision: 1.4
Phase 5 complete (gateway + HandoffPort + SPT runaway/prod guards). Soak checklist remains open for ship score 10.
Alert LLM routing added: needs_human | auto_infra (kagent handoff, no delete) | ignore — tested with FakeLlm.
Temporal lab: ready on kind-am-preprod (`default` ns registered)
