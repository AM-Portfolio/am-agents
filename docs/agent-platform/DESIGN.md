# Agnostic Temporal agent platform — Design SoT

**Repo:** `am-agents`  
**Revision:** 1.1  
**Status:** DESIGN — privacy/sandbox gaps closed in ADR-002; awaiting confirmation before Phase 0 code  
**Phase gate:** docs + diagrams first; ports/code only after explicit approve

Related: [../ENTERPRISE_AGENT_ECOSYSTEM.md](../ENTERPRISE_AGENT_ECOSYSTEM.md) · Obs Grafana SoT: **am-obs-platform** (`docs/PLATFORM_DESIGN.md`)

## Design source of truth

Everything for this platform is under **`docs/agent-platform/`** (this folder).

| What | File |
|------|------|
| **Index** | [README.md](README.md) |
| **This design** | [DESIGN.md](DESIGN.md) |
| **ADR** | [ADR-001 ports](decisions/ADR-001-temporal-agent-ports.md) · [ADR-002 privacy/sandbox](decisions/ADR-002-privacy-sandbox-secrets.md) |
| **Phases** | [PHASES.md](PHASES.md) |
| **Folder structure (all phases)** | [FOLDER_STRUCTURE.md](FOLDER_STRUCTURE.md) |
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
| Docs home | **`am-agents/docs/agent-platform/`** only |
| Extractable SDK | **ADR-003** — `libs/platform-ports` (+ agent-common, platform-adapters); any agent can depend; later publish/move without rewrite |
| Privacy / secrets | **ADR-002** — LLM never sees env/creds; SecretBroker + ToolSandbox + Redactor |
| Tool execution | All queries/side effects via **ToolSandbox** |
| LLM access | **LlmPort** only (gateway) |

## Design principles

1. Workflows are vendor-blind — activities call ports only.
2. One agent → one job — Temporal owns e2e durability.
3. Adapters at the edge — env-selected (`TICKET_PROVIDER`, `DOC_PROVIDER`, `PROMPT_PROVIDER`, …).
4. Opaque refs — `ticket_ref`, `docs_ref`, `workflow_id`, …
5. Ship vertical slices — each phase ends with lab smoke.
6. No duplicate logic — one module owns each concern.
7. Modular hexagonal layout — extends obs ADR-011 patterns.
8. Design SoT in **`am-agents/docs/agent-platform/`** — one folder (md + sheets + drawio).
9. **Privacy by default** — reasoning plane never receives secrets or raw env (ADR-002).
10. **Sandbox all tools** — no direct privileged API/subprocess from agent/LLM code.

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
| Creds | Never in prompts, Temporal payloads, Cliq, docs, Langfuse raw traces |
| Env | Never pass `os.environ` / worker env into LLM or sandbox |
| Secrets | `secret_ref` only in workflows; resolve inside adapters via SecretBroker |
| Tools | Deny-by-default allowlist; network egress allowlist; output redaction |
| Data class | `public` / `internal` / `sensitive` / `secret` — secret never to LLM |
| Audit | Log tool name + redacted args + workflow_id; never log secret values |

**Still thin vs big-tech (track, not blockers for Phase 1 MVP):** multi-tenant isolation, formal threat model doc, eval/red-team suite, confidential compute — Phase 5+.

## Design review — gaps (updated)

| Gap | Severity | Status |
|-----|----------|--------|
| No SecretBroker / creds could leak to LLM | P0 | **Closed** — ADR-002 |
| No ToolSandbox (direct env to tools) | P0 | **Closed** — ADR-002 |
| No LlmPort / Redactor on prompt path | P0 | **Closed** — ADR-002 |
| Dual notify formatters (infra vs platform) | P1 | Open — Phase 1 |
| OP status map not filled | P1 | Ops checklist |
| Temporal not deployed | P1 | Phase 1 |
| FailoverDocStore ledger for docs_provider | P2 | Phase 2 |
| Prompt catalog empty | P2 | Phase 0–1 |
| Observe query templates | P2 | Phase 3 |
| Multi-tenant / RBAC on gateway | P3 | Phase 5 |

## Phases

| Phase | Ship | Done when |
|-------|------|-----------|
| **0a Docs** | Design md + mmd + drawio + ADR-001…004 | Confirm before code — detail: [PHASES.md](PHASES.md) |
| **0b Ports** | `libs/platform-ports` + agent-common + adapters stubs + SPT schemas/fakes | CI green; other agents can depend on ports |
| **1 MVP** | Temporal + AlertIncident + OpenProject + Cliq | FIRING → ticket + Cliq ≤ 60s; RESOLVED |
| **2** | DocStore MinIO+GDrive + infra + Approve | Doc on ticket; allowlisted infra |
| **3** | SPT catalog/selectors + fan-out + partial-failure + prep_ref + growth CI | Lab smoke ≥2 children + partial; `spt-growth` CI green |
| **4** | Jira + Zoho Mail + Calendar | Same workflows; env swap |
| **5** | L2 gateway + handoffs + prod SPT + soak | Policy-gated; soak checklist for ship 10 |

## Package boundaries

Full tree: **[FOLDER_STRUCTURE.md](FOLDER_STRUCTURE.md)** · Extractable SDK: **[ADR-003](decisions/ADR-003-extractable-sdk.md)**.

| Package | Owns | Forbidden |
|---------|------|-----------|
| `libs/platform-ports` (`am_platform_ports`) | Protocols + schemas + fakes | Worker, adapters, env, SDKs |
| `libs/agent-common` | OTel/HTTP helpers | Vendor SDKs |
| `libs/platform-adapters` | `build_*` + providers + SecretBroker | Workflows; secrets to LLM |
| `platform_worker` | Temporal workflows/activities | Agents importing providers |
| `catalog/prompts/` | Prompt content | Python bodies |
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
| tool_agent | InfraOps plan/execute/verify |
| fin_agent | DataPrep once |
| spt_agent | Load test run |
| observe_agent | Metrics/logs → AnalysisReport |

## Confirmation gate

```text
Status: AWAITING CONFIRMATION
Approved by: —
Approved at: —
Approved design revision: 1.3 (ADR-002 privacy + ADR-003 extractable SDK + ADR-004 SPT)
Next step after approve: Phase 0b — libs/platform-ports first (reusable by any agent)
```

Reply **approve design** (or request changes) before any Protocol/adapter implementation. Checklist: [PHASES.md](PHASES.md).
