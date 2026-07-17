# Agent platform (Temporal) — design package

**One folder.** No parallel `docs/design/` vs `docs/diagrams/` for this topic.

| File | Role |
|------|------|
| [DESIGN.md](DESIGN.md) | Design SoT + confirmation gate |
| [PHASES.md](PHASES.md) | Phase checklist |
| [FOLDER_STRUCTURE.md](FOLDER_STRUCTURE.md) | Complete tree all phases (P0–P5) |
| [decisions/ADR-001-temporal-agent-ports.md](decisions/ADR-001-temporal-agent-ports.md) | Ports ADR |
| [decisions/ADR-002-privacy-sandbox-secrets.md](decisions/ADR-002-privacy-sandbox-secrets.md) | Privacy / sandbox / no creds to LLM |
| [decisions/ADR-003-extractable-sdk.md](decisions/ADR-003-extractable-sdk.md) | Extractable SDK — other agents reuse ports |
| [decisions/ADR-005-runstore-verify.md](decisions/ADR-005-runstore-verify.md) | RunStore ledger + post-fix verify gate A |
| [sheets/modules.mmd](sheets/modules.mmd) | Owns / does-not-own |
| [sheets/e2e.mmd](sheets/e2e.mmd) | AlertIncident E2E (+ RunStore + verify) |
| [sheets/ports.mmd](sheets/ports.mmd) | Ports + factories |
| [sheets/runstore.mmd](sheets/runstore.mmd) | RunStore intake / steps / verify |
| [sheets/docstore.mmd](sheets/docstore.mmd) | MinIO → GDrive failover |
| [sheets/prompts.mmd](sheets/prompts.mmd) | Prompt registry |
| [agent-platform.drawio](agent-platform.drawio) | Multi-page Draw.io |

## Draw.io pages

Four Layers · Module Owns / Not · AlertIncident E2E · Ports + Factories · **RunStore + Verify** · DocStore Failover · Prompt Registry · Phases 0–5 · Anti-dupe Rules

## Elsewhere (do not mix)

| Topic | Location |
|-------|----------|
| Enterprise portals / surfaces | [`../diagrams/`](../diagrams/) |
| Grafana / Alert Ops | `am-obs-platform/docs/` |
