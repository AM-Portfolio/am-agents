# ADR-004: SPT catalog + selectors

**Status:** Accepted (locks SPT agnostic design)  
**Date:** 2026-07-18  
**Parent:** [../DESIGN.md](../DESIGN.md) · Related: [ADR-001](ADR-001-temporal-agent-ports.md) · [ADR-002](ADR-002-privacy-sandbox-secrets.md) · [ADR-005](ADR-005-runstore-verify.md)

## Context

The platform must run performance / load tests across many services (tens of repos, hundreds of targets) without baking service names into worker or ports code. Failures must be partial-safe; prep must be shared where catalogs say so; runaway “run all” must be impossible by default.

## Decision

### 1. Catalog + selectors only

- **Code never names** repos or services. Targets live in `catalog/spt/` (services + flows).
- Requests use **`SptDemandRequest.selector`**: `ids` and/or `tags` only.
- **Empty selector = fatal** (no implicit all).
- `selector: { all: true }` rejected unless `env=lab` **and** `Approve` **and** expanded count ≤ `SPT_MAX_TARGETS_PER_RUN`.

### 2. Ports

| Port | Role |
|------|------|
| `TargetCatalog` | Read catalog entries |
| `TargetResolver` | Expand selector → TargetSet |
| `LoadPolicy` | Per-target allow / skip |
| `LoadTestRunner` | Run scenario via ToolSandbox (e.g. k6) |
| `DataPrep` | `ensure_dataset(prep_ref)` |
| `ObservabilityPort` | `query_ref` metrics/logs |

Schemas: `SptDemandRequest`, `ChildRunResult`, `SptRunSummary`, `failure_mode`. Every SPT demand also **`RunStore.create_run(kind=spt)`** (ADR-005).

### 3. Partial-failure (locked)

| Rule | Behavior |
|------|----------|
| Default `failure_mode` | `continue` — siblings keep running (bounded parallelism) |
| `fail_fast` | Cancel pending after first **failed**; mark rest `cancelled` |
| `skipped` | Policy deny / `enabled: false` — not a hard fail |
| `overall_status` | `succeeded` if failed=0 and succeeded≥1; `partial` if both; `failed` if succeeded=0 and failed≥1; empty TargetSet = fatal before run |
| Notify | `spt.completed` always includes counts — never false all-green on partial |
| Retries | Only **retryable** child errors; fatal → child failed, continue siblings under `continue` |

### 4. `prep_ref` (locked)

Optional opaque string on service/flow catalog entries.

| Rule | Behavior |
|------|----------|
| Missing | Skip DataPrep; load only |
| Present | `DataPrep.ensure_dataset(prep_ref)` **once per distinct prep_ref per parent run** |
| Shared | Same `prep_ref` → one prep, shared `dataset_ref` |
| Failure | Prep fatal → those targets failed/skipped; other prep groups unaffected under `continue` |
| Secrets | Via SecretBroker inside prep adapter; never to LLM |

### 5. Runaway guards (locked)

| Guard | Rule |
|-------|------|
| `SPT_MAX_TARGETS_PER_RUN` | Default **20**; prod **5** until policy raises |
| `SPT_MAX_PARALLEL` | Default **5** |
| Tag expansion > max | `needs_human` / reject — never silent truncate |
| Prod catalog | `enabled: false` default; Approve + change window; mandatory observe + doc |
| `SPT_MAX_CONCURRENT_RUNS` | Cap concurrent parent runs (e.g. 3 lab / 1 prod) |
| Audit | Log selector hash + `expanded_count` (redacted); alert if expansion > max |

### 6. Growth / CI (Phase 3)

- Growth test: add catalog YAML → TargetSet grows; worker/ports paths unchanged.
- No-hardcode lint: no real service/repo ids in `platform_worker/` or `libs/platform-ports/`.
- JSON Schema validate `catalog/spt/services/*.yaml`.

### 7. Lab acceptance (Phase 3)

≥2 children, `parallelism: 2`; intentional partial → parent `partial` + correct counts; 3 lab services (2 share `prep_ref`) + 1 flow.

## Consequences

- Phase 0b: SPT schemas/ports stubs in `am_platform_ports` (done).
- Phase 3: file catalog, k6 via sandbox, `SptRunWorkflow` fan-out, growth CI.
- Phase 5: prod Approve + soak checklist for ship score 10.
- Checklist: [../PHASES.md](../PHASES.md) Phase 3 / 5.
