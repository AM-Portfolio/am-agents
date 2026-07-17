# Agnostic Temporal agent platform — Design SoT

**Repo:** `am-agents`  
**Revision:** 1.4  
**Status:** DESIGN — RunStore + verify-after-fix locked (ADR-005); awaiting confirmation before Phase 0b code  
**Phase gate:** docs + diagrams first; ports/code only after explicit approve

Related: [../ENTERPRISE_AGENT_ECOSYSTEM.md](../ENTERPRISE_AGENT_ECOSYSTEM.md) · Obs Grafana SoT: **am-obs-platform** (`docs/PLATFORM_DESIGN.md`)

## Design source of truth

Everything for this platform is under **`docs/agent-platform/`** (this folder).

| What | File |
|------|------|
| **Index** | [README.md](README.md) |
| **This design** | [DESIGN.md](DESIGN.md) |
| **ADR** | [ADR-001](decisions/ADR-001-temporal-agent-ports.md) · [ADR-002](decisions/ADR-002-privacy-sandbox-secrets.md) · [ADR-003](decisions/ADR-003-extractable-sdk.md) · [ADR-005 RunStore](decisions/ADR-005-runstore-verify.md) |
| **Phases** | [PHASES.md](PHASES.md) |
| **Folder structure (all phases)** | [FOLDER_STRUCTURE.md](FOLDER_STRUCTURE.md) |
| **Mermaid** | [sheets/](sheets/) especially [runstore.mmd](sheets/runstore.mmd) |
| **Draw.io** | [agent-platform.drawio](agent-platform.drawio) |

## Locked decisions

| Decision | Choice |
|----------|--------|
| Orchestration | Temporal workflows call **ports only** |
| Run ledger | **`RunStore`** → Postgres `agent_runs` + `agent_run_steps` ([ADR-005](decisions/ADR-005-runstore-verify.md)) |
| Intake | Every request (AlertIncident / SPT / verify) **creates run with initial status** before heavy work |
| Step updates | Each activity → upsert step + roll up parent; claim loop for `pending` |
| Post-fix verify | After `work_done` → `kind=verify` (metrics, logs, …); **gate A** blocks done until pass / Approve |
| Tickets | `TicketStore` — OpenProject first; Jira = adapter later |
| Chat notify | `Notifier` — Cliq; **follow-up cards only** (no edit API v1) |
| Docs | `DocStore` — **MinIO primary** (local), **Google Drive failover** (not dual-write) |
| Prompts | `PromptRegistry` — content in catalog, **not in code**; Langfuse/`http` adapters |
| Observe | Grafana **HTTP** adapter only for ObservabilityPort v1 |
| Edge | Alert Ops (am-obs-platform): `StartWorkflow` / `SignalWorkflow` only |
| Structure | Hexagonal; one composition root; no duplicate port/formatter forks |
| Docs home | **`am-agents/docs/agent-platform/`** only |
| Extractable SDK | **ADR-003** — `libs/platform-ports` (+ agent-common, platform-adapters) |
| Privacy / secrets | **ADR-002** — LLM never sees env/creds; SecretBroker + ToolSandbox + Redactor |
| Tool execution | All queries/side effects via **ToolSandbox** |
| LLM access | **LlmPort** only (gateway) |

## Design principles

1. Workflows are vendor-blind — activities call ports only.
2. One agent → one job — Temporal owns e2e durability.
3. Adapters at the edge — env-selected (`TICKET_PROVIDER`, `DOC_PROVIDER`, `RUN_STORE_PROVIDER`, …).
4. Opaque refs — `ticket_ref`, `docs_ref`, `run_ref`, `workflow_id`, …
5. Ship vertical slices — each phase ends with lab smoke.
6. No duplicate logic — one module owns each concern.
7. Modular hexagonal layout — extends obs ADR-011 patterns.
8. Design SoT in **`am-agents/docs/agent-platform/`** — one folder (md + sheets + drawio).
9. **Privacy by default** — reasoning plane never receives secrets or raw env (ADR-002).
10. **Sandbox all tools** — no direct privileged API/subprocess from agent/LLM code.
11. **RunStore on every Start** — never work without an initial status row (ADR-005).

## Security & agentic rules (big-tech baseline)

```text
                    ┌─────────────────────────────┐
  Temporal / edge → │ Control plane (secrets OK)  │ → adapters + SecretBroker
                    │ ToolSandbox (scrubbed env)  │ → allowlisted APIs only
                    └──────────────┬──────────────┘
                                   │ sanitized tool results only
                    ┌──────────────▼──────────────┐
                    │ Reasoning plane (LLM)       │  NO env, NO tokens
                    │ LlmPort + Redactor          │
                    └─────────────────────────────┘
```

| Rule | Requirement |
|------|-------------|
| Creds | Never in prompts, Temporal payloads, Cliq, docs, Langfuse raw traces, **RunStore rows** |
| Env | Never pass `os.environ` / worker env into LLM or sandbox |
| Secrets | `secret_ref` only in workflows; resolve inside adapters via SecretBroker |
| Tools | Deny-by-default allowlist; network egress allowlist; output redaction |
| Data class | `public` / `internal` / `sensitive` / `secret` — secret never to LLM |
| Audit | Log tool name + redacted args + workflow_id + run_ref; never log secret values |

**Still thin vs big-tech (track, not blockers for Phase 1 MVP):** multi-tenant isolation, formal threat model doc, eval/red-team suite, confidential compute — Phase 5+.

## Design review — gaps (updated)

| Gap | Severity | Status |
|-----|----------|--------|
| No SecretBroker / creds could leak to LLM | P0 | **Closed** — ADR-002 |
| No ToolSandbox (direct env to tools) | P0 | **Closed** — ADR-002 |
| No LlmPort / Redactor on prompt path | P0 | **Closed** — ADR-002 |
| No durable run/step status ledger | P0 | **Closed** — ADR-005 RunStore |
| No post-fix verification before done | P1 | **Closed (design)** — ADR-005 gate A; ship Phase 2 |
| Dual notify formatters (infra vs platform) | P1 | Open — Phase 1 |
| OP status map not filled | P1 | Ops checklist |
| Temporal not deployed | P1 | Phase 1 |
| FailoverDocStore ledger for docs_provider | P2 | Phase 2 |
| Prompt catalog empty | P2 | Phase 0–1 |
| Observe / verify query templates | P2 | Phase 2–3 |
| Multi-tenant / RBAC on gateway | P3 | Phase 5 |

## Phases

| Phase | Ship | Done when |
|-------|------|-----------|
| **0a Docs** | Design md + mmd + drawio + ADR-001…005 | Confirm before code — detail: [PHASES.md](PHASES.md) |
| **0b Ports** | `libs/platform-ports` + RunStore schemas/fakes + stubs | CI green; other agents can depend on ports |
| **1 MVP** | Temporal + AlertIncident + create_run + OP + Cliq | FIRING → run row + ticket + Cliq ≤ 60s; RESOLVED |
| **2** | DocStore + InfraOps + **verify run** (metrics/logs) + Postgres RunStore | Gate A: done only after verify pass |
| **3** | SPT catalog/selectors + fan-out + RunStore step updates + growth CI | Lab smoke ≥2 children + partial; `spt-growth` CI green |
| **4** | Jira + Zoho Mail + Calendar | Same workflows; env swap |
| **5** | L2 gateway + handoffs + prod SPT + soak | Policy-gated; soak checklist for ship 10 |

## Package boundaries

Full tree: **[FOLDER_STRUCTURE.md](FOLDER_STRUCTURE.md)** · Extractable SDK: **[ADR-003](decisions/ADR-003-extractable-sdk.md)**.

| Package | Owns | Forbidden |
|---------|------|-----------|
| `libs/platform-ports` (`am_platform_ports`) | Protocols + schemas + fakes | Worker, adapters, env, SDKs |
| `libs/agent-common` | OTel/HTTP helpers | Vendor SDKs |
| `libs/platform-adapters` | `build_*` + providers + SecretBroker + Postgres RunStore | Workflows; secrets to LLM |
| `platform_worker` | Temporal workflows/activities | Agents importing providers |
| `catalog/prompts/` · `catalog/verify/` | Prompt / check content | Python bodies |
| `gateway` (P5) | Start/Signal/status + auth | Business steps |
| am-obs-platform | Grafana + Alert Ops edge | Hosting agent port SDK |
| am-infra | Helm/K8s only | App logic |

## Agent catalog (single responsibility)

| Agent | Owns only |
|-------|-----------|
| triage_agent | Classify + priority |
| ticket_agent | TicketStore CRUD/assign |
| docs_agent | DocStore |
| notify_agent | Notifier |
| tool_agent | InfraOps plan/execute |
| verify_agent | Verify steps (metrics/logs/health) via catalog `check_ref` |
| fin_agent | DataPrep once |
| spt_agent | Load test run |
| observe_agent | Metrics/logs → AnalysisReport (SPT / shared ObservabilityPort) |

**RunStore** is a platform port (not an agent): workflows write intake + step status; claim loop pulls `pending`.

## Confirmation gate

```text
Status: AWAITING CONFIRMATION
Approved by: —
Approved at: —
Approved design revision: 1.4 (ADR-002 + ADR-003 + ADR-005; ADR-004 SPT pending file)
Next step after approve: Phase 0b — libs/platform-ports first (reusable by any agent)
```

Reply **approve design** (or request changes) before any Protocol/adapter implementation. Checklist: [PHASES.md](PHASES.md).
