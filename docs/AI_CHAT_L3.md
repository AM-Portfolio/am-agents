# AI chat — am-agents notes (feature/ai-chat-l3)

Finance L3 remains **`fin-portfolio-agent`** in this repo (no redefine / no move).

| Concern | Location |
|---------|----------|
| L3 agent | `am-agents/fin-portfolio-agent` — `POST /api/v1/ai/chat` on **8101** |
| Tool discovery | Java `am-mcp-server` via MCP `list_tools` (TTL cache in fin-agent) |
| artifactType map | `fin-portfolio-agent/shared/formatters/artifact_resolver.py` |
| L2 AI gateway | **`am-gateways/mcp-gateway`** (deploy name **am-ai-gateway**) on **8120** — not here |
| Product REST edge | `am-gateways/api-gateway` (deploy **am-api-gateway**) — do not redefine asrax |

UI (`am-modern-ui`) prefers config `aiGateway` → 8120; Phase 1 may call 8101 via `financeAgent`.

Smoke: see `am-modern-ui/docs/AI_CHAT_SMOKE.md`.
