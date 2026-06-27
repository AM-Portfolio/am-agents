# Architecture diagrams (Draw.io)

All architecture visuals are in **one multi-page Draw.io file** — switch pages via tabs at the bottom of the editor.

## Single file (all pages)

**[enterprise-agent-ecosystem.drawio](enterprise-agent-ecosystem.drawio)**

| Page tab | Content |
|----------|---------|
| Enterprise Master - Agents Features Integrations | All agents, integrations, features, lifecycle, company memory |
| Three Surfaces Overview | Three surfaces, gateway, agents, L4, execution flow |
| Four Layers | L1–L4 ownership boundaries |
| B2B Routing | B2B: employees → Portal B, end users → A, SRE → C |
| Portal B Screens | Portal B tabs and backends |
| Chat Flow | Chat request SSE sequence |
| Integration Flow | IntegrationsHub connect + status |
| DevOps Dual Entry | Portal B chat vs kagent — same am-infra-ops brain |
| Repo Reuse | Which repo maps to which portal |
| Phases | Phase 0–5 timeline |
| URL RBAC | Hosts, portals, role access |

## How to open

1. **Cursor / VS Code:** [Draw.io Integration](https://marketplace.visualstudio.com/items?itemName=hediet.vscode-drawio) → open `enterprise-agent-ecosystem.drawio`
2. **Browser:** [app.diagrams.net](https://app.diagrams.net) → Open Existing Diagram

Use the **page tabs** at the bottom to navigate between diagrams.

## Export for docs

**File → Export as → PNG** or **SVG** (export current page, or all pages).
