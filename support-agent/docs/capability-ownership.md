# Capability ownership matrix

**Rule:** Support-agent orchestrates; tool-agent executes vendor I/O behind generic capability IDs; vendors appear only as adapters.

Last frozen: 2026-07-18

## Who owns what

| Owner | Owns | Does not own |
|-------|------|--------------|
| **support-agent** | Workflows, HITL, policy, post-assignment validation, context intelligence, Postgres working/episodic memory, notification composition, handoff lineage, A2A planner/router | Vendor SDKs, OpenProject/Zoho/Cliq/MinIO details |
| **tool-agent** | Generic plugins + `adapters/<vendor>/` | Incident decisions, HITL, learning promotion |
| **shared platform** (`libs/platform-ports`, `libs/platform-adapters`) | Portable ports + reusable providers, secret/redaction abstractions | Support-agent Temporal workflow semantics |
| **Langfuse** | Runtime prompt bodies (labels/versions) | Business policy decisions |
| **Postgres** | Workflow/task ledger + episode/feedback stores | Semantic embeddings (Qdrant is post-canary) |

## Neutral capability IDs → adapters

| Capability ID | Tool plugin | First adapter | Later |
|---------------|-------------|---------------|-------|
| `work-item.*` | `work-item` | `openproject` | `jira` |
| `directory.owner.resolve` | `directory` | `openproject` | — |
| `chat.message.send` / `chat.card.send` | `chat` | `cliq` | — |
| `mail.message.send` | `mail` | `zoho` | — |
| `calendar.event.create` | `calendar` | `zoho` | optional |
| `document.*` | `document` | `minio` | `gdrive` post-canary |
| `observe.metrics.query` / `observe.logs.query` / `observe.timeseries.query` | `observe` | `grafana` / `prometheus` / `influx` | — |
| `spt.test-data.prepare` / `spt.execute` / `spt.status` / `spt.cancel` | `spt` | `k6` | — |
| `secret.*` admin | existing `vault` | `vault` | — |

Support-agent-only (never tool plugins): `verification.evaluate`, `reasoning.generate`, `prompt.resolve`, `workflow.handoff`, `notification.compose`.

## Incident acceptance gate (mandatory)

After `work-item.assign`, support-agent must:

1. Call `work-item.get` and verify assignment/correlation against the provider response.
2. Gather observe evidence (Grafana metrics/logs) + directory/catalog context.
3. Build `IncidentContext` and persist `IncidentValidation`.
4. Branch: `confirmed` → notify/act; `inconclusive` → HITL; `not_confirmed` → annotate and stop.

Typed contracts live in:

- [`src/am_support_agent/contracts/capabilities.py`](../src/am_support_agent/contracts/capabilities.py)
- [`src/am_support_agent/contracts/incident.py`](../src/am_support_agent/contracts/incident.py)
- [`src/am_support_agent/contracts/enums.py`](../src/am_support_agent/contracts/enums.py) (`CapabilityId`, `IncidentValidationStatus`)

## Lean runtime (first canary)

Temporal + Grafana observe + Langfuse + Postgres + tool-agent.

Deferred post-canary: Qdrant semantic index, full learning promotion UI, Jira, GDrive.

## Related docs

- [MIGRATION_MAP.md](../MIGRATION_MAP.md)
- [run-store.md](run-store.md)
- [parity.md](parity.md)
- [contracts/README.md](../contracts/README.md)
