# Production gates, rollback, and decommission

**Status:** Phase 0 gate specification  
**Hard rule:** Existing code stays intact until every gate below passes **and** explicit multi-party approval is recorded.

## Parallel deployment constraints

| Constraint | Requirement |
|------------|-------------|
| Service identity | Distinct Deployment / Service names from legacy gateway/worker |
| Temporal | Distinct task queue (example: `agent-platform-v2`) until cutover |
| Credentials | Distinct Vault paths / tokens |
| Data | Distinct RunStore schema/namespace or clearly versioned tables; no silent overwrite of legacy rows |
| Traffic | Feature flag / route split; legacy remains default until canary expands |
| Specialists | Tool / DB / UI agents unchanged and shared by both paths |

## Phase gates

### Gate A — Non-production validation

Must pass before any production traffic:

- [ ] Contract / schema tests for A2A envelopes and agent cards
- [ ] Integration tests against Tool / DB / UI HTTP APIs (adapters only)
- [ ] E2E AlertIncident and SPT parity scenarios vs legacy path
- [ ] Failure injection: specialist timeout, 5xx, partial fan-out, cancel
- [ ] Security: auth reject, allowlist deny, secret redaction checks
- [ ] Load / concurrency within documented budgets
- [ ] Idempotent retry of `execute` with same `idempotency_key`
- [ ] Rollback drill: disable new path; legacy path serves 100%

### Gate B — Production shadow

- [ ] New path receives mirrored requests **without** side-effecting tickets/chat/infra (or with dry-run adapters)
- [ ] Decision / plan / evidence compared to legacy for allowlisted sample
- [ ] Documented parity threshold met (correctness, not just HTTP 200)
- [ ] No unresolved Sev-1/2 from shadow period

### Gate C — Production canary

- [ ] Small allowlisted workload on new path
- [ ] Error rate, p95 latency, cost/run, queue lag, availability within SLO
- [ ] Operator sign-off after canary window
- [ ] Instant route flip back to legacy rehearsed

### Gate D — Production soak + cutover

- [ ] New path at 100% **intended** production traffic
- [ ] Agreed soak window with no unresolved Sev-1/2, no data loss, no security regression
- [ ] Legacy path still deployed, healthy, and immediately routable
- [ ] Rollback rehearsal successful during soak

### Gate E — Decommission (separately approved)

Eligible for review **only** when Gates A–D are complete. Decommission is **not** implied by merge, deploy, or soak alone.

Required approvals (all):

1. User / product owner
2. Agent service owners (Tool / DB / UI as applicable)
3. Platform operations

Checklist:

- [ ] Deletion inventory: files, Deployments, Services, CronJobs, Vault paths, Temporal queues, DB tables, dashboards owned by **legacy platform path only**
- [ ] Explicit exclusion: `tool-agent/`, `db-agent/`, `ui-test-agent/` — **never deleted** here
- [ ] Backups / archive of required run history and config
- [ ] Disable legacy traffic first → observe → then delete approved resources
- [ ] Post-delete verification: new path healthy; no dangling refs

## SLO targets (baseline — tune in ops review)

| Signal | Target (initial) |
|--------|------------------|
| Availability (gateway) | ≥ 99.5% monthly |
| p95 end-to-end AlertIncident start→first ticket/notify | ≤ legacy p95 × 1.2 |
| Error rate (platform tasks) | ≤ legacy + 0.5 pp |
| Cost per successful run | ≤ legacy × 1.15 |
| Data loss incidents | 0 |

## Rollback ownership

| Role | Action |
|------|--------|
| On-call platform | Flip traffic / feature flag to legacy within minutes |
| Orchestrator owner | Pause new Temporal queue consumers if needed |
| Specialist owners | No change required for platform rollback |

## What this phase does **not** authorize

- Editing application code, Helm values, or CI workflows
- Deleting or renaming `gateway/`, `platform_worker/`, or shared libs
- Changing Tool / DB / UI Test agent implementations
- Auto-promotion of learning candidates to production
