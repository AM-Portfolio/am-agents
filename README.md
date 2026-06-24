# am-agents

Unified home for AM AI agents.

| Agent | Location | Port / entry | Status |
|-------|----------|--------------|--------|
| **db-agent** | [`db-agent/`](db-agent/) | HTTP `:8140` | **Implemented** (Phase 2a) |
| UI test | [`../am-ui-test-agent/`](../am-ui-test-agent/) | HTTP `:8130` | Legacy (monorepo copy planned) |
| Finance | [`../am-fin-agent/`](../am-fin-agent/) | HTTP `:8100` | Legacy |
| Dev CLI | [`../am-dev-agent/`](../am-dev-agent/) | `am-dev` CLI | Legacy |

## Documentation

- **[Monorepo implementation plan](docs/MONOREPO_PLAN.md)** — Phase 1: full copy into `am-agents/`, npm workspaces
- **[Universal DB agents plan](docs/UNIVERSAL_DB_AGENTS_PLAN.md)** — MCP catalog, phases
- **[db-agent design spec](docs/DB_AGENT_DESIGN.md)** — API, LangGraph, registry, safety

## db-agent quick start

From **`am-agents/`** (monorepo root):

```bash
cd am-agents
pip install -r db-agent/requirements.txt
npm run start:preprod
```

Or from **`am-agents/db-agent/`**:

```bash
npm run preprod
```

Logs: `db-agent/logs/db-agent/<timestamp>_preprod.log` — clean with `npm run logs:clean`
