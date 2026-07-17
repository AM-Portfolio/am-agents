# Complete folder structure (all phases)

**SoT for layout.** Phases add folders; they do **not** invent a second parallel tree.  
Existing agents (`tool-agent/`, `db-agent/`, `ui-test-agent/`) stay; new Temporal platform nests beside them.

Legend: `[P0]` … `[P5]` = first phase that introduces the path. Paths without a tag already exist or are docs-only.

---

## Repo map (who owns what)

| Repo / package | Role |
|----------------|------|
| **am-agents/libs/platform-ports** | **Extractable SDK** — Protocols + schemas + fakes (any agent may depend) |
| **am-agents/libs/agent-common** | Extractable helpers (OTel/HTTP) |
| **am-agents/libs/platform-adapters** | `build_*` + vendor adapters (optional extras; SecretBroker inside) |
| **am-agents/platform_worker** | Temporal app — depends on ports (+ adapters at runtime) |
| **am-agents/catalog/prompts** | Prompt data (not a Python package of logic) |
| **am-agents/gateway** | P5 — Temporal client only |
| **am-obs-platform** | Alert Ops edge + Grafana content; may *consume* platform-ports for notify types |
| **am-infra** | Helm/K8s only |

**Reuse rule:** other agents import **`am_platform_ports` only**. They do not need Temporal or adapters to share contracts. Later: publish/move `libs/platform-ports` to its own repo without changing imports (ADR-003).

---

## 1. `am-agents` (full target)

```text
am-agents/
├── docs/agent-platform/                       # [P0a] design SoT
│   ├── FOLDER_STRUCTURE.md
│   ├── DESIGN.md
│   ├── decisions/ADR-001 … ADR-003
│   └── …
│
├── libs/
│   ├── platform-ports/                        # [P0b] EXTRACTABLE SDK ★
│   │   ├── pyproject.toml                     # name = am-platform-ports
│   │   ├── src/am_platform_ports/
│   │   │   ├── ports/                         # Protocols only
│   │   │   │   ├── triage.py
│   │   │   │   ├── ticket.py
│   │   │   │   ├── notifier.py
│   │   │   │   ├── directory.py
│   │   │   │   ├── policy.py
│   │   │   │   ├── prompt.py
│   │   │   │   ├── secret.py
│   │   │   │   ├── sandbox.py
│   │   │   │   ├── redact.py
│   │   │   │   ├── llm.py
│   │   │   │   ├── docs.py                   # [P2]
│   │   │   │   ├── infra.py                  # [P2]
│   │   │   │   ├── prep.py                   # [P3]
│   │   │   │   ├── loadtest.py               # [P3]
│   │   │   │   ├── observe.py                # [P3]
│   │   │   │   ├── mail.py                   # [P4]
│   │   │   │   ├── calendar.py               # [P4]
│   │   │   │   └── handoff.py                # [P5]
│   │   │   ├── schemas/                       # pydantic DTOs
│   │   │   ├── fakes/
│   │   │   └── testing/                       # contract test base classes
│   │   └── tests/contract/
│   │
│   ├── agent-common/                          # [P0b] EXTRACTABLE
│   │   └── src/agent_common/
│   │
│   └── platform-adapters/                     # [P0b+] EXTRACTABLE (heavier)
│       ├── pyproject.toml                     # extras: openproject,cliq,minio,gdrive,jira,…
│       └── src/am_platform_adapters/
│           ├── factory.py                     # build_* composition root
│           ├── secret/vault.py
│           ├── sandbox/
│           ├── redactor.py
│           ├── failover_docstore.py           # [P2]
│           └── providers/
│               ├── openproject/               # [P1]
│               ├── cliq/                      # [P1]
│               ├── langfuse/                  # [P1]
│               ├── llm_gateway/               # [P1]
│               ├── minio/                     # [P2]
│               ├── gdrive/                    # [P2]
│               ├── grafana_observe/           # [P3]
│               ├── jira/                      # [P4]
│               ├── zoho_mail/                 # [P4]
│               └── zoho_calendar/             # [P4]
│
├── catalog/prompts/                           # [P0b] data only
├── platform_worker/                           # [P1] Temporal app
│   └── src/platform_worker/
│       ├── di.py                              # imports am_platform_adapters.factory
│       ├── workflows/
│       ├── activities/
│       ├── agents/                            # thin; import am_platform_ports only
│       └── sandbox/                           # thin wrapper → adapters sandbox
├── gateway/                                   # [P5]
├── tool-agent/                                # [exists] — later: depend on am_platform_ports
├── db-agent/
└── ui-test-agent/
```

### How another agent reuses (today + after extract)

```text
# any agent (tool-agent, db-agent, new)
# pyproject.toml:
#   dependencies = ["am-platform-ports"]

from am_platform_ports.ports.ticket import TicketStore
from am_platform_ports.fakes.ticket import FakeTicketStore
# optional runtime:
#   am-platform-adapters[openproject]
```

Later extract: move `libs/platform-ports` → own git repo / private PyPI; **imports stay `am_platform_ports.*`**.

---

## 2. `am-obs-platform` (edge + Grafana only — not the agent SDK)

Agent ports/adapters live in **am-agents/libs/** (ADR-003). Obs keeps Grafana publish + Alert Ops hook.

```text
am-obs-platform/
├── docs/                                      # Grafana/Alert Ops SoT only
├── platform_ctl/
│   ├── adapters.py                            # AlertRule / Silence / Notify for Grafana path
│   └── ports/alerting.py                      # [exists] Grafana publish ports only
├── providers/
│   ├── cliq/                                  # [exists] lab notify; align with adapters package later
│   └── grafana/                               # dashboards / silence / observe reuse [P3]
└── apps/alerting-runtime/
    └── src/alerting_runtime/relay/
        ├── handler.py                         # [P1] StartWorkflow / Signal (+ existing notify)
        ├── temporal_client.py                 # [P1]
        └── notify_format.py                   # card render SoT for Alert Ops
```

Optional later: Alert Ops depends on `am-platform-ports` + `am-platform-adapters[cliq]` so Cliq is not duplicated.

---

## 3. `am-infra` (deploy only)

```text
am-infra/
└── k8s/
    ├── temporal/                              # [P1]
    ├── minio/                                 # [P2]
    ├── agent-platform/
    │   ├── platform-worker/                   # [P1]
    │   └── agent-gateway/                     # [P5]
    └── grafana/alert-ops/
```

---

## 4. What must never appear

| Forbidden | Why |
|-----------|-----|
| Agent ports inside `am-obs-platform/platform_ctl/ports/` | Blocks extraction; use `libs/platform-ports` |
| Per-agent fork of `am_platform_ports` | Anti-dupe / ADR-003 |
| `platform-ports` importing worker or providers | Breaks extract + other-agent reuse |
| Secrets in workflows / Temporal payloads | ADR-002 |
| Prompt bodies in Python | PromptRegistry |
| `am-obs-platform/docs/agent-platform/` | Docs only in am-agents |

---

## 5. Phase → folders cheat sheet

| Phase | Adds |
|-------|------|
| **0a** | `docs/agent-platform/**` (done) |
| **0b** | `libs/platform-ports`, `libs/agent-common`, `libs/platform-adapters` (stubs), `catalog/prompts`, contract tests |
| **1** | `platform_worker` workflows/activities, OP/Cliq/Vault/Langfuse/LLM adapters, Alert Ops temporal_client |
| **2** | DocStore + InfraOps ports/adapters, docs/tool agents |
| **3** | SPT workflow + prep/loadtest/observe |
| **4** | Jira + Zoho mail/calendar |
| **5** | `gateway/`, HandoffPort — **optional: publish platform-ports to private PyPI** |

---

## 6. Dependency direction (import rules)

```text
any agent / platform_worker.agents  →  am_platform_ports          ✗ adapters
platform_worker.di / runtime        →  am_platform_adapters.factory
am_platform_adapters.providers      →  am_platform_ports + SecretBroker
am_platform_ports                   →  (pydantic only)            ✗ everything else
gateway                             →  Temporal client            ✗ providers
tool-agent (future)                 →  am_platform_ports (+ optional adapters)
```
