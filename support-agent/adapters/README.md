# Adapters

Adapters are the **only** bridge from the Platform Orchestrator to specialist agents. They must not require changes inside `tool-agent/`, `db-agent/`, or `ui-test-agent/`.

## Implementation

| Adapter | Module | Status |
|---------|--------|--------|
| `tool_agent` | `src/am_support_agent/adapters/` (`ToolAgentAdapter`) | ✅ |
| `db_agent` | `DbAgentAdapter` + caller header | ✅ |
| `ui_test_agent` | `UiTestAgentAdapter` (synthesize plan, poll status) | ✅ |
| `storage` | `adapters/storage.py` DocStore prefix + RunStore note | ✅ boundary |
| `llm` | `adapters/llm.py` gated probe | ✅ gate |

## Responsibilities

| Adapter | Calls | Compensates |
|---------|-------|-------------|
| `tool_agent` | `/api/v1/tools/{query,plan,execute}` + streams + health | discover card, status correlation, cancel/feedback at platform layer |
| `db_agent` | `/api/v1/db/{query,plan,execute}` + health | same; enforce `legacy.db-agent` gate before use |
| `ui_test_agent` | `/api/v1/test/run`, status, report | synthesize plan; poll→stream; document non-HA status |
| `storage` | A2A TaskRunStore + MinIO DocStore prefix | map memory ports; distinct v2 namespace when parallel |
| `llm` | existing LlmPort adapters | redaction before prompts; composition root 📄 |

## Non-responsibilities

- Reimplementing specialist tools
- Writing into specialist process memory
- Bypassing ToolSandbox / SecretBroker rules from ADR-002
- Importing `platform_worker` or mutating specialist repos

## Auth / idempotency

- Attach service identity required by each specialist
- Persist `idempotency_key` → specialist correlation in RunStore
- Timeouts from task `budget.max_latency_ms`
