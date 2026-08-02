# am-agents

Unified home for AM AI agents and the Agent Platform.

| Component | Location | Port / entry | Status |
|-----------|----------|--------------|--------|
| **tool-agent** | [`tool-agent/`](tool-agent/) | HTTP `:8141` | **Active** — preferred data/tool executor |
| **db-agent** | [`db-agent/`](db-agent/) | HTTP `:8140` | **Legacy** — compatibility; prefer tool-agent |
| **support-agent** | [`support-agent/`](support-agent/) | Gateway v2 `:8091` · queue `support-agent-v2` | **Active** |
| **fin-portfolio-agent** | [`fin-portfolio-agent/`](fin-portfolio-agent/) | HTTP `:8101` — finance L3 AI chat | **Active** |
| **Agent Platform (legacy path)** | [`gateway/`](gateway/) + [`platform_worker/`](platform_worker/) | Gateway `:8090` · Temporal queue `agent-platform` | **Keep until replacement proven** |

**AI chat layout:** finance L3 stays in this repo (`fin-portfolio-agent`). The L2 AI
gateway lives in **`am-gateways/mcp-gateway`** (deploy **am-ai-gateway**) — do not redefine
`api-gateway` / asrax. Tool SoT is Java **am-mcp-server** (`list_tools`); see
[`catalog/finance/`](catalog/finance/) (docs only) and [`docs/AI_CHAT_L3.md`](docs/AI_CHAT_L3.md).

QA Specs / UI evidence / SPT moved to **[am-qa-agents](https://github.com/AM-Portfolio/am-qa-agents)** (`qa-agent/specs`, `qa-agent/ui_evidence`).

## Documentation

- **[Architecture (A2A + parallel replacement)](docs/architecture/)** — terminology, A2A protocol, execution flow, production/decommission gates
- **[support-agent/ module](support-agent/)** — A2A replacement tree, migration map, adapters, memory, learning, decommission checklist
- **[Agent platform Temporal design SoT](docs/agent-platform/)** — ports, RunStore, AlertIncident phases (historical + current legacy path)
- **[Enterprise agent ecosystem](docs/ENTERPRISE_AGENT_ECOSYSTEM.md)** — gap analysis, anti-duplication
- **[Deploy guide](docs/DEPLOY.md)** — Docker, Helm, Vault, CI/CD
- **[Monorepo plan](docs/MONOREPO_PLAN.md)** — historical copy-in plan (superseded for inventory by this README + architecture docs)
- **[db-agent design](docs/DB_AGENT_DESIGN.md)** · **[Universal DB agents plan](docs/UNIVERSAL_DB_AGENTS_PLAN.md)**

## Parallel replacement rule

1. **Markdown / design first** for the new module (current).
2. Build **complete** `support-agent/` **alongside** existing gateway/worker — do not edit specialist agents.
3. Shadow → canary → soak in production with rollback to legacy.
4. **Delete** legacy platform code only after [production gates](docs/architecture/production-gates.md) + explicit approvals. Never delete Tool / DB / support specialists.

## Platform ports (legacy SDK)

```bash
cd libs/platform-ports
pip install -e ".[dev]"
pytest
```

Package: `am_platform_ports` — Protocols + schemas + fakes (no Temporal / no vendors).

## Quick starts

### tool-agent (preferred)

```bash
cd tool-agent
pip install -r requirements.txt
# see tool-agent/README.md for env + npm scripts
```

### db-agent (legacy)

```bash
cd am-agents
pip install -r db-agent/requirements.txt
npm run start:preprod
```

### support-agent

```bash
cd support-agent
# see support-agent/README.md
```

### fin-portfolio-agent

```bash
cd fin-portfolio-agent
pip install -r requirements.txt
# see fin-portfolio-agent/README.md — chat on :8101
```
