# ADR-003 — Extractable platform SDK (reuse by any agent)

**Status:** Proposed (locks packaging)  
**Date:** 2026-07-18  
**Parent:** [DESIGN.md](../DESIGN.md) · [FOLDER_STRUCTURE.md](../FOLDER_STRUCTURE.md)

## Context

Ports must not be buried inside `am-obs-platform` or a single worker app. Other agents (`tool-agent`, `db-agent`, future agents) and a future standalone repo must consume the same contracts without copy-paste. Extraction later must be a **package move**, not a rewrite.

## Decision

### 1. Three installable libs under `am-agents/libs/` (P0b)

| Package | Import name | Contains | Depends on |
|---------|-------------|----------|------------|
| **platform-ports** | `am_platform_ports` | Protocols, schemas, fakes, contract test helpers | pydantic only |
| **agent-common** | `agent_common` | OTel, logging, scrubbed HTTP helper | stdlib + light deps |
| **platform-adapters** | `am_platform_adapters` | `build_*`, providers, SecretBroker/Vault, FailoverDocStore, Redactor impl | platform-ports + agent-common |

### 2. Consumers

| Consumer | May depend on |
|----------|----------------|
| `platform_worker`, gateway, any agent | `am_platform_ports` (+ fakes in tests) |
| Worker runtime / composition | `am_platform_adapters` (optional extra) |
| LLM / agent reasoning code | **`am_platform_ports` only** — never adapters |
| am-obs-platform Alert Ops | `am_platform_ports` for shared Notifier types; keep Grafana AlertRulePublisher local until migrated |

### 3. Extraction path (later, no rewrite)

```text
am-agents/libs/platform-ports  →  repo am-platform-ports (or publish to private PyPI)
am-agents/libs/agent-common      →  same or sibling package
am-agents/libs/platform-adapters →  adapters repo / extras
```

Rules so extraction stays easy:

- Stable import paths: `from am_platform_ports.ports.ticket import TicketStore`
- No imports from `platform_worker`, `tool-agent`, or `am-obs-platform` **into** `platform-ports`
- Adapters selected by env extras: `pip install am-platform-adapters[openproject,cliq,minio]`
- Versioned semver; contract tests ship **with** platform-ports

### 4. What stays out of the SDK

- Temporal workflows (app-specific)
- Prompt **content** (`catalog/prompts` — data plane)
- Helm charts, Vault values
- Grafana compiler / Alert Ops UI (obs-platform)

## Consequences

- Phase 0b creates `libs/platform-ports` first (not ports inside obs `platform_ctl`).
- Obs `platform_ctl/ports/alerting.py` remains for Grafana publish; agent ports do **not** live there.
- Other agents adopt by adding dependency + using ports/fakes — no Temporal required.
