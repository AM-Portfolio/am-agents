# Agent platform (Temporal) — design package

**One folder.** No parallel `docs/design/` vs `docs/diagrams/` for this topic.

| File | Role |
|------|------|
| [decisions/ADR-003-extractable-sdk.md](decisions/ADR-003-extractable-sdk.md) | Extractable SDK — other agents reuse ports |
| [FOLDER_STRUCTURE.md](FOLDER_STRUCTURE.md) | Complete tree all phases (P0–P5) |
| [DESIGN.md](DESIGN.md) | Design SoT + confirmation gate |
| [PHASES.md](PHASES.md) | Phase checklist |
| [decisions/ADR-001-temporal-agent-ports.md](decisions/ADR-001-temporal-agent-ports.md) | Ports ADR |
| [decisions/ADR-002-privacy-sandbox-secrets.md](decisions/ADR-002-privacy-sandbox-secrets.md) | Privacy / sandbox / no creds to LLM |
| [sheets/modules.mmd](sheets/modules.mmd) | Owns / does-not-own |
| [sheets/e2e.mmd](sheets/e2e.mmd) | AlertIncident E2E |
| [sheets/ports.mmd](sheets/ports.mmd) | Ports + factories |
| [sheets/docstore.mmd](sheets/docstore.mmd) | MinIO → GDrive failover |
| [sheets/prompts.mmd](sheets/prompts.mmd) | Prompt registry |
| [agent-platform.drawio](agent-platform.drawio) | Multi-page Draw.io |

## Draw.io pages

Four Layers · Module Owns / Not · AlertIncident E2E · Ports + Factories · DocStore Failover · Prompt Registry · Phases 0–5 · Anti-dupe Rules

## Elsewhere (do not mix)

| Topic | Location |
|-------|----------|
| Enterprise portals / surfaces | [`../diagrams/`](../diagrams/) |
| Grafana / Alert Ops | `am-obs-platform/docs/` |
