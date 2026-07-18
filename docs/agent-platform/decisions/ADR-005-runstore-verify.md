# ADR-005: RunStore + post-fix verification

**Status:** Proposed (locks ledger + verify gate)  
**Date:** 2026-07-18  
**Parent:** [../DESIGN.md](../DESIGN.md)

## Context

AlertIncident, SPT, and later gateway requests need an ops-visible status ledger beyond Temporal history. After a fix, the platform must verify recovery (Grafana metrics, logs, health, …) before treating the incident as done. A vague “task table” collides with TicketStore naming.

## Decision

1. **`RunStore` port** → Postgres tables `agent_runs` + `agent_run_steps` (opaque `run_ref` / `step_ref`).
2. **Intake rule:** every accepted request (`alert_incident` | `spt` | `verify` | …) **creates a run row with initial status** before heavy work.
3. **Step rule:** after each meaningful activity, **upsert step + roll up parent** status (idempotent for Temporal retries).
4. Temporal remains the orchestrator; RunStore is the **ledger + claim queue** for `pending` work (`FOR UPDATE SKIP LOCKED` + lease).
5. After InfraOps `work_done`, spawn linked `kind=verify` run; steps use catalog `check_ref` via ObservabilityPort (metrics/logs) and ToolSandbox probes.
6. **Verify gate A:** block “done” / success notify until verify `passed` or human Approve override.

## Schema (logical)

```text
agent_runs: run_ref, kind, status, parent_run_ref?, incident_ref?, ticket_ref?,
            demand_ref?, workflow_id?, requested_selector_hash?, summary_json?
agent_run_steps: step_ref, run_ref, name_or_kind, check_ref?, status,
                 claim_lease_until?, worker_id?, attempts, last_error_class?, result_ref?
```

Statuses: `pending | accepted | claimed | running | passed | partial | failed | skipped | cancelled | needs_human`.

## Consequences

- Phase 0b: RunStore Protocol + fakes; Phase 1: create_run on AlertIncident Start; Phase 2: Postgres + verify claim loop; Phase 3: SPT create_run + step updates aligned with `SptRunSummary`.
- No secrets in RunStore rows (ADR-002).
- Diagrams: [../sheets/runstore.mmd](../sheets/runstore.mmd), Draw.io page **RunStore + Verify**.
