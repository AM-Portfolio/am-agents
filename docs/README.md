# am-agents docs

| Area | Path | What |
|------|------|------|
| **Architecture (A2A + parallel replacement)** | [architecture/](architecture/) | Terminology, A2A, execution flow, production/decommission gates |
| **support-agent module** | [`../support-agent/`](../support-agent/) | Complete tree, migration map, adapters, memory, learning, decommission |
| **Agent platform (Temporal SoT)** | [agent-platform/](agent-platform/) | Design SoT, ADR, Mermaid sheets, Draw.io — legacy path design |
| **Enterprise ecosystem** | [ENTERPRISE_AGENT_ECOSYSTEM.md](ENTERPRISE_AGENT_ECOSYSTEM.md) · [diagrams/](diagrams/) | Portals / surfaces Draw.io |
| Monorepo / deploy | [MONOREPO_PLAN.md](MONOREPO_PLAN.md) · [DEPLOY.md](DEPLOY.md) · [CONNECTING.md](CONNECTING.md) | Ops notes (monorepo plan is historical) |
| DB agents | [DB_AGENT_DESIGN.md](DB_AGENT_DESIGN.md) · [UNIVERSAL_DB_AGENTS_PLAN.md](UNIVERSAL_DB_AGENTS_PLAN.md) | DB agent plans |
| Per-agent | `tool-agent/docs/`, `ui-test-agent/docs/` | Tool-specific |

Grafana / observability design stays in **am-obs-platform** — not duplicated here.

**Hard rule:** Build the replacement alongside existing code; delete legacy platform code only after production gates + explicit approval. Never delete Tool / DB / UI Test agents.
