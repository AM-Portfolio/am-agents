# ADR-001 — Temporal agent platform ports

**Status:** Proposed (awaiting design confirmation)  
**Date:** 2026-07-18  
**Repo:** am-agents  
**Related:** am-obs-platform ADR-011 (alerting ports pattern)

## Context

Agents need durable orchestration (tickets, notify, docs, SPT, observe) without baking OpenProject, Cliq, MinIO, Google Drive, or Langfuse into workflow code. Design docs and diagrams for this platform live in **`am-agents/docs/agent-platform/`** only.

## Decision

1. **Hexagonal ports** — Protocols + pydantic schemas; adapters at the edge; one composition root (`build_*` from env).
2. **Temporal** workflows/activities call ports only. Opaque refs: `ticket_ref`, `docs_ref`, `workflow_id`, …
3. **PromptRegistry** — agents hold prompt **keys** only; content in git catalog + publish; `PROMPT_PROVIDER=langfuse|http|fake`.
4. **DocStore** — `DOC_PROVIDER=minio` primary; `DOC_FALLBACK=gdrive` via `FailoverDocStore` (not dual-write).
5. **Notifier** — Cliq follow-up cards only in v1; one render path.
6. **TicketStore** — OpenProject first; Jira = second adapter, not a fork.
7. **Anti-duplication** — no per-agent Protocol copies; shared agent-common; contract tests against fake + real adapters.
8. **Phase gate** — design under `am-agents/docs` confirmed before Protocol implementation.

## Ports (Phase 0–1 MVP)

- TriagePort, DirectoryPort, TicketStore, Notifier, PolicyPort, PromptRegistry  
- Phase 2+: DocStore, InfraOps, DataPrep, LoadTestRunner, ObservabilityPort  

## Consequences

- Swap vendor = new adapter + env flag.
- Coding ports starts only after design confirmation on [DESIGN.md](../DESIGN.md).
