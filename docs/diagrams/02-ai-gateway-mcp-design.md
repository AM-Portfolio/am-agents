# AI Gateway + MCP Architecture

If the `.drawio` file appears blank in GitHub or your browser, open it locally in Cursor/VS Code with the **Draw.io Integration** extension, or use [app.diagrams.net](https://app.diagrams.net) → **File → Open from → Device**.

Also available inside the working master file: `enterprise-agent-ecosystem.drawio` → page **AI Gateway Architecture**.

Try the compressed variant if needed: `02-ai-gateway-mcp-design-compressed.drawio`

---

## Target architecture (Mermaid)

```mermaid
flowchart TB
    subgraph L1["L1 — Client Surfaces"]
        UI["Web UI — am-modern-ui"]
        IDE["IDE — Cursor / VS Code"]
        MOB["Mobile (future)"]
        PB["Portal B — ai-bots"]
    end

    subgraph AUTH["Auth & Security"]
        KC["Keycloak JWT + RBAC"]
        GR["AI Guardrails"]
    end

    subgraph L2["L2 — am-mcp-gateway :8120 (am-platform)"]
        CHAT["POST /api/v1/chat/stream"]
        REG["Prompt Registry — agents.yaml"]
        ROUTE["Intent Router"]
        SEC["AI Security"]
        SSE["Unified SSE"]
        LLM["LLM Proxy"]
        MCP["MCP Proxy"]
        CHAT --> REG --> ROUTE --> SEC --> SSE --> LLM --> MCP
    end

    subgraph L3["L3 — Domain Agents (am-agents)"]
        FIN["fin-agent :8100"]
        TEST["ui-test-agent :8130"]
        TOOL["tool-agent :8141"]
        DEV["ai-bots dev :5000"]
    end

    subgraph L4["L4 — MCP Core Services"]
        PORT["Portfolio SDK"]
        TRADE["Trade"]
        VAULT["Vault MCP"]
        K8S["K8s MCP"]
        DB["DB MCP Toolbox"]
    end

    subgraph PLAT["Platform"]
        LIT["LiteLLM"]
        LF["Langfuse"]
    end

    UI --> KC
    IDE --> KC
    PB --> KC
    KC --> GR --> CHAT
    ROUTE --> FIN
    ROUTE --> TEST
    ROUTE --> TOOL
    FIN --> PORT
    TOOL --> VAULT
    LLM --> LIT --> LF
```

## Chat request flow

```mermaid
sequenceDiagram
    participant U as User
    participant UI as am-modern-ui
    participant GW as am-mcp-gateway
    participant A as fin-agent
    participant M as Portfolio SDK
    participant L as LiteLLM

    U->>UI: Show my portfolio PnL
    UI->>GW: POST /api/v1/chat/stream + JWT
    GW->>GW: Auth + RBAC + route finance
    GW->>A: Proxy SSE request
    A->>M: tool_call get_holdings
    M-->>A: holdings data
    A->>GW: POST /agent/llm/completions
    GW->>L: LLM reasoning
    L-->>A: completion
    A-->>GW: SSE token, artifact, done
    GW-->>UI: Unified SSE stream
    UI-->>U: Widget + summary
```

## Whiteboard mapping

| Whiteboard | Implementation |
|---|---|
| AI Gateway | `am-platform/am-mcp-gateway` |
| fin-agent | `am-fin-agent` / `fin-portfolio-agent` |
| MCP server | tool-agent + fin MCP + LiteLLM registry |
| Prompt Registry | `agents.yaml` (planned) |
| LiteLLM / billing | LiteLLM + Langfuse via gateway |
| Modern UI | `am-modern-ui` Flutter ai-chat |
