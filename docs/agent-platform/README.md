# Agent platform (Temporal) — design package

**One folder.** No parallel `docs/design/` vs `docs/diagrams/` for this topic.

| File | Role |
|------|------|
| [DESIGN.md](DESIGN.md) | Design SoT + confirmation gate |
| [PHASES.md](PHASES.md) | Phase checklist |
| [decisions/ADR-001-temporal-agent-ports.md](decisions/ADR-001-temporal-agent-ports.md) | ADR |
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
