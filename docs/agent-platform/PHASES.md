# Agent platform — phase checklist

Parent: [DESIGN.md](DESIGN.md) · Index: [README.md](README.md)  
**Docs home:** `am-agents/docs/agent-platform/` only

## Phase 0a — Design docs (current)

- [x] Single folder `docs/agent-platform/` (no duplicate `design/` + `diagrams/` split)
- [x] `DESIGN.md` + `PHASES.md` + `decisions/ADR-001-…`
- [x] `sheets/*.mmd` + `agent-platform.drawio`
- [x] `docs/README.md` index; enterprise diagrams stay under `docs/diagrams/`
- [ ] **User confirmation** — approve design before 0b

## Phase 0b — Ports (blocked on confirmation)

- [ ] Ports + schemas + fakes + contract tests
- [ ] PromptRegistry Protocol + fake
- [ ] Minimal `agent-common` stub (no forks)

## Phase 1 — AlertIncident MVP

- [ ] Temporal lab + worker
- [ ] AlertIncidentWorkflow + Alert Ops Start/Signal hook
- [ ] OpenProject TicketStore + Directory; Cliq Notifier
- [ ] Flap / silence / race state machine
- [ ] Lab smoke: FIRING → ticket + Cliq ≤ 60s; RESOLVED

## Phase 2 — Docs + infra

- [ ] DocStore MinIO + FailoverDocStore → GDrive
- [ ] InfraOps + Approve signal
- [ ] `work_done` on agent.resolved

## Phase 3 — SPT

- [ ] SptRunWorkflow + Grafana ObservabilityPort HTTP
- [ ] Report via DocStore

## Phase 4 — Jira / Mail / Calendar

- [ ] Jira TicketStore adapter
- [ ] Zoho Mail + Calendar ports

## Phase 5 — Gateway / handoff / prod SPT

- [ ] L2 chat gateway
- [ ] HandoffPort max depth 1
- [ ] Policy-gated prod SPT
