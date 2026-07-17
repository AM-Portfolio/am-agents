# Agnostic Temporal agent platform — Design SoT

**Repo:** `am-agents`  
**Revision:** 1.0  
**Status:** DESIGN — awaiting confirmation before Phase 0 code  
**Phase gate:** docs + diagrams first; ports/code only after explicit approve

Related: [../ENTERPRISE_AGENT_ECOSYSTEM.md](../ENTERPRISE_AGENT_ECOSYSTEM.md) · Obs Grafana SoT: **am-obs-platform** (`docs/PLATFORM_DESIGN.md`)

## Design source of truth

Everything for this platform is under **`docs/agent-platform/`** (this folder).

| What | File |
|------|------|
| **Index** | [README.md](README.md) |
| **This design** | [DESIGN.md](DESIGN.md) |
| **ADR** | [decisions/ADR-001-temporal-agent-ports.md](decisions/ADR-001-temporal-agent-ports.md) |
| **Phases** | [PHASES.md](PHASES.md) |
| **Mermaid** | [sheets/](sheets/) |
| **Draw.io** | [agent-platform.drawio](agent-platform.drawio) |

## Locked decisions

| Decision | Choice |
|----------|--------|
| Orchestration | Temporal workflows call **ports only** |
| Tickets | `TicketStore` — OpenProject first; Jira = adapter later |
| Chat notify | `Notifier` — Cliq; **follow-up cards only** (no edit API v1) |
| Docs | `DocStore` — **MinIO primary** (local), **Google Drive failover** (not dual-write) |
| Prompts | `PromptRegistry` — content in catalog, **not in code**; Langfuse/`http` adapters |
| Observe | Grafana **HTTP** adapter only for ObservabilityPort v1 |
| Edge | Alert Ops (am-obs-platform): `StartWorkflow` / `SignalWorkflow` only |
| Structure | Hexagonal; one composition root; no duplicate port/formatter forks |
| Docs home | **`am-agents/docs/agent-platform/`** only — not obs-platform, not a second `design/`/`diagrams/` split |

## Design principles

1. Workflows are vendor-blind — activities call ports only.
2. One agent → one job — Temporal owns e2e durability.
3. Adapters at the edge — env-selected (`TICKET_PROVIDER`, `DOC_PROVIDER`, `PROMPT_PROVIDER`, …).
4. Opaque refs — `ticket_ref`, `docs_ref`, `workflow_id`, …
5. Ship vertical slices — each phase ends with lab smoke.
6. No duplicate logic — one module owns each concern.
7. Modular hexagonal layout — extends obs ADR-011 patterns.
8. Design SoT in **`am-agents/docs/agent-platform/`** — one folder (md + sheets + drawio).

## Phases

| Phase | Ship | Done when |
|-------|------|-----------|
| **0a Docs** | Design md + mmd + drawio in am-agents | This gate — **confirm before code** |
| **0b Ports** | Protocols + schemas + fakes + contract tests | CI green with fakes |
| **1 MVP** | Temporal + AlertIncident + OpenProject + Cliq | FIRING → ticket + Cliq ≤ 60s; RESOLVED |
| **2** | DocStore MinIO+GDrive + infra + Approve | Doc on ticket; allowlisted infra |
| **3** | SPT + Grafana observe + report | Prep→run→analyze→DocStore→Cliq |
| **4** | Jira + Zoho Mail + Calendar | Same workflows; env swap |
| **5** | L2 gateway + handoffs + prod SPT | Policy-gated |

## Package boundaries

| Package | Owns | Forbidden |
|---------|------|-----------|
| Shared ports/schemas (platform_ctl or am-agents libs) | Protocols + DTOs | SDK / HTTP / env |
| `providers/<vendor>/` or agent adapters | Adapters | Workflow rules |
| Composition root `build_*` | Env → factories | Business logic |
| Temporal worker (this repo) | Workflows + activities via ports | Vendor SDKs direct |
| `catalog/prompts/` | Prompt content | Python |
| Alert Ops edge (am-obs-platform) | Start/Signal + ledger | Ticket/triage/docs |

## Agent catalog (single responsibility)

| Agent | Owns only |
|-------|-----------|
| triage_agent | Classify + priority |
| ticket_agent | TicketStore CRUD/assign |
| docs_agent | DocStore |
| notify_agent | Notifier |
| tool_agent | InfraOps plan/execute/verify |
| fin_agent | DataPrep once |
| spt_agent | Load test run |
| observe_agent | Metrics/logs → AnalysisReport |

## Confirmation gate

```text
Status: AWAITING CONFIRMATION
Approved by: —
Approved at: —
Approved design revision: 1.0
Docs location: am-agents/docs/agent-platform/
Next step after approve: Phase 0b — ports/schemas/fakes + contract tests
```

Reply **approve design** (or request changes) before any Protocol/adapter implementation.
