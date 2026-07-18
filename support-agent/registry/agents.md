# Agent registry design

**Phase 0:** Documented here. Concrete `agents.yaml` is created in the code-authorized phase.

## Intended `registry/agents.yaml` shape

```yaml
version: 1
defaults:
  prefer: tool-agent
  budgets:
    max_fanout: 8
    max_latency_ms: 120000
    max_cost_units: 100

agents:
  - agent_id: tool-agent
    display_name: Tool Agent
    base_url_env: TOOL_AGENT_BASE_URL
    default_port: 8141
    preferred: true
    health_path: /health
    ready_path: /ready
    capabilities:
      - id: tools.plan
        ops: [discover, plan, execute, stream]
      - id: tools.execute
        ops: [discover, plan, execute, stream]
      - id: tools.query
        ops: [discover, execute, stream]
    limits:
      multi_replica_status: false

  - agent_id: db-agent
    display_name: DB Agent (legacy)
    base_url_env: DB_AGENT_BASE_URL
    default_port: 8140
    preferred: false
    tags: [legacy.db-agent]
    health_path: /health
    ready_path: /ready
    auth:
      caller_header: X-Agent-Caller
    capabilities:
      - id: db.plan
        ops: [discover, plan, execute]
      - id: db.execute
        ops: [discover, plan, execute]
    limits:
      multi_replica_status: false

  - agent_id: ui-test-agent
    display_name: UI Test Agent
    base_url_env: UI_TEST_AGENT_BASE_URL
    default_port: 8130
    preferred: true
    health_path: /health
    capabilities:
      - id: ui.test.run
        ops: [discover, plan, execute, status, stream]
      - id: ui.test.report
        ops: [discover, status]
    limits:
      multi_replica_status: false   # process-local status store

integrations:
  kagent_mcp:
    description: Declarative kagent agents call Tool Agent via MCP bridge
    mcp_url_env: TOOL_AGENT_MCP_URL
    default_port: 8085
    executor: tool-agent
```

## Allowlist rule

Orchestrator may invoke only `agents[].agent_id` entries present in this registry for the active environment. Unknown agents → reject.
