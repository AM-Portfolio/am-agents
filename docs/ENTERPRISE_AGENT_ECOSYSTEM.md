# AM Enterprise Agent Ecosystem — Full Design & Phased Execution Plan

**Status:** Approved design — ready for phased execution  
**Audience:** Engineering, platform, product, SRE  
**Last updated:** 2026-06-17 (added §2.6 operating modes, §3 complete agent catalog)

**Doc map:** §2 Architecture & modes · §3 All agents (detailed) · §14 Meeting integration · §4 Inventory · §7 Phases · §10 Execution · [Master diagram (Draw.io)](diagrams/enterprise-agent-ecosystem.drawio)

**Related:** [MONOREPO_PLAN.md](MONOREPO_PLAN.md), [tool-agent MCP_CONTRACT.md](../tool-agent/docs/MCP_CONTRACT.md), [kagent README](../k8s/kagent/README.md), [ai-video-editor architecture](../../ai-video-editor/video_pipeline/docs/architecture.md), [diagrams/README.md](diagrams/README.md)

**Architecture diagram:** [diagrams/enterprise-agent-ecosystem.drawio](diagrams/enterprise-agent-ecosystem.drawio) (master) · [diagrams/README.md](diagrams/README.md) (full index)

---

## 1. Vision

One company platform where specialist agents serve **three audiences** through **three surfaces**, all backed by the **same gateway and company memory**. End users get a simple product experience (Portal A); internal teams get chat plus integrations (Portal B); SRE/infra get deep K8s ops (Portal C). A **Scribe agent** captures meetings and requirements into **company memory** that downstream agents read from discovery through release and beyond.

**Lifecycle:** Discovery → Requirements → Development → Test → Release → Marketing → Support → Admin → Feedback loop.

**UI strategy:** **Three surfaces, one gateway** — see [§2.7 UI strategy](#27-ui-strategy-three-surfaces-one-gateway).

---

## 2. Target architecture (enterprise-grade)

### 2.1 Four layers — single ownership

> **Diagram (Draw.io):** [enterprise-agent-ecosystem.drawio](diagrams/enterprise-agent-ecosystem.drawio) (page **Four Layers**)


| Layer | Owns | Never owns |
|-------|------|------------|
| **L1 UI** | Chat, artifacts, requirements board, meeting panel | Agent logic, tool calls, LLM prompts |
| **L2 Gateway** | Auth, routing, SSE normalization, sessions, Langfuse root span | Domain reasoning, infra SDKs |
| **L3 Domain** | Prompts, LangGraph/workflow, domain tool selection | Mongo/kafka clients, FFmpeg, direct Together/Gemini |
| **L4 Capability** | MCP/REST tools, plan/execute endpoints | Personality, user-facing chat |

### 2.2 Standard agent contract (every domain agent)

All L3 agents implement the same HTTP interface so the gateway never needs agent-specific code paths beyond routing.

```
POST /api/v1/agent/chat          → JSON response (non-stream)
POST /api/v1/agent/chat/stream   → SSE (preferred)
GET  /health
GET  /ready
```

**Request (gateway → agent):**

```json
{
  "message": "user text",
  "sessionId": "uuid",
  "userId": "keycloak-sub",
  "traceId": "uuid",
  "agentContext": {
    "pinnedAgent": null,
    "requirementIds": ["REQ-001"],
    "workingSummary": "optional cross-agent context"
  }
}
```

**SSE events (agent → gateway → UI) — one schema for all agents:**

| Event | Payload | When |
|-------|---------|------|
| `agent_selected` | `{ "agent": "devops" }` | Router chose agent |
| `stage` | `{ "name": "planning", "detail": "..." }` | Pipeline step started |
| `tool_call` | `{ "tool": "...", "status": "running\|done\|error" }` | Capability invoked |
| `token` | `{ "text": "..." }` | Streaming markdown |
| `artifact` | `{ "type": "widget\|table\|report\|video", "data": {} }` | Rich output |
| `memory_update` | `{ "requirementId": "...", "status": "..." }` | Lifecycle change |
| `done` | `{ "traceId", "toolsUsed", "agent" }` | Turn complete |

**Pattern reference:** tool-agent plan/execute + ai-video-editor planner/executor/explainer + fin-agent widget artifacts.

### 2.3 Company memory (single source of truth)

One service — **not** duplicated in Notion, Jira, and local files without sync.

**Store:** Postgres (authoritative) + Qdrant (semantic search)  
**API:** `am-company-memory` (can start as gateway module, extract later)

| Entity | Key fields |
|--------|------------|
| `meetings` | id, title, datetime, transcript, source (upload/bot/slack) |
| `requirements` | id, title, text, acceptance_criteria[], owner_agent, status, meeting_id |
| `decisions` | id, meeting_id, text, decided_at |
| `lifecycle_events` | requirement_id, phase, agent, timestamp, artifact_url |
| `action_items` | requirement_id, assignee, task, due_date, ticket_url |

**Status enum:** `draft` → `approved` → `in_progress` → `tested` → `released` → `supported`

**Rule:** Jira/Linear are **sync targets**, not primary store. Scribe writes memory first; MCP pushes tickets outward.

### 2.4 Agent registry (`agents.yaml`)

Single file in gateway — no hardcoded routes in `chat.py`.

```yaml
agents:
  - id: scribe
    name: Scribe
    endpoint: http://am-scribe-agent.am-apps-preprod.svc:8150
    roles: [all]
    keywords: [meeting, requirement, transcript, standup, decision]
    capabilities: [company-memory, video-transcribe]

  - id: finance
    name: Finance
    endpoint: http://am-fin-agent.am-apps-preprod.svc:8100
    roles: [user, finance]
    keywords: [portfolio, holdings, pnl, trade]
    artifact_types: [widget]

  - id: devops
    name: DevOps
    endpoint: http://am-devops-agent.am-apps-preprod.svc:8151  # thin wrapper
    roles: [engineering, sre]
    keywords: [pod, deploy, kafka, vault, grafana, cluster]
    capabilities: [tool-agent, k8s-mcp]
    workflow: plan_then_execute

  - id: test
    name: Test
    endpoint: http://am-ui-test-agent.am-apps-preprod.svc:8130
    roles: [engineering, qa]
    keywords: [test, playwright, regression, ui]
    capabilities: [ui-test-runner]

  - id: dev
    name: Dev
    endpoint: http://am-dev-agent.am-apps-preprod.svc:8152
    roles: [engineering]
    keywords: [implement, code, pr, fix, feature]
    capabilities: [github-mcp, company-memory]

  - id: marketing
    name: Marketing
    endpoint: http://am-marketing-agent.am-apps-preprod.svc:8153
    roles: [marketing]
    keywords: [campaign, landing, email, launch, content]
    capabilities: [video-agent, company-memory]

  - id: support
    name: Support
    endpoint: http://am-support-agent.am-apps-preprod.svc:8154
    roles: [support]
    keywords: [ticket, customer, refund, faq]
    capabilities: [crm-mcp, company-memory]

  - id: admin
    name: Admin
    endpoint: http://am-admin-agent.am-apps-preprod.svc:8155
    roles: [admin]
    keywords: [access, compliance, invoice, hr]
    capabilities: [company-memory]
```

### 2.5 Capability registry (L4 — build once, use many)

| Capability | Source | Port | MCP tools / REST | Consumers |
|------------|--------|------|------------------|-----------|
| **tool-agent** | `am-agents/tool-agent` | 8141 | `tool_agent_plan`, `tool_agent_execute`, … | devops, test, dev |
| **video-agent** | `ai-video-editor/video_pipeline` | 8156 | `video_transcribe`, `video_plan_edit`, `video_execute` | scribe, marketing |
| **k8s MCP** | kagent RemoteMCPServer | 8085 | `k8s_get_*` | devops |
| **company-memory** | new | 8157 | `memory_search`, `memory_get_req`, `memory_update` | all L3 |
| **github MCP** | satellite | — | `create_pr`, `search_code` | dev |
| **jira MCP** | satellite | — | `create_issue` | scribe, dev, support |

### 2.6 Operating modes (gateway, agents, capabilities)

Every agent and capability supports explicit **modes**. Modes are configured in `agents.yaml` or env — not hardcoded per UI.

#### 2.6.1 Gateway routing modes

| Mode | Trigger | Behavior |
|------|---------|----------|
| **auto** | Default; no `pinnedAgent` in request | Keyword match → optional LLM classify → highest-confidence agent |
| **pinned** | UI sidebar or `agentContext.pinnedAgent` | Skip classify; route directly to named agent |
| **handoff** | User says "now run tests" mid-thread | Router switches agent; gateway injects `workingSummary` from Redis session |
| **fallback** | Target agent down / timeout | Gateway logs Langfuse error; falls back to general LLM or returns `ERROR` artifact |

#### 2.6.2 Streaming modes

| Mode | Endpoint | Used by |
|------|----------|---------|
| **SSE stream** | `POST /api/v1/chat/stream` | Enterprise UI (default) |
| **JSON batch** | `POST /api/v1/chat` | Mobile low-bandwidth, webhooks |
| **Passthrough SSE** | Agent-native stream wrapped by gateway | fin-agent, devops-agent during Phase 1 migration |

Gateway normalizes all streams to the event schema in §2.2 regardless of agent-native format.

#### 2.6.3 tool-agent capability modes

| Mode | API | When to use |
|------|-----|-------------|
| **plan** | `POST /api/v1/tools/plan[/stream]` | DevOps, audit — show intent before execute |
| **execute** | `POST /api/v1/tools/execute[/stream]` | After plan approved or intent known |
| **query** | `POST /api/v1/tools/query[/stream]` | IDE one-shot only; **not** for kagent/devops-agent |
| **MCP stream** | `TOOL_AGENT_MCP_USE_STREAM=true` | MCP bridge returns `stages[]` array |

Policy: **devops-agent always plan → execute** for infra backends (matches am-infra-ops).

#### 2.6.4 Domain agent workflow modes

| Agent | Workflow mode | Description |
|-------|---------------|-------------|
| scribe | **extract** | Transcript → structured REQ/decisions/actions (no execute) |
| finance | **ReAct + widget** | LangGraph tool loop → deterministic `widgetId` mapping |
| devops | **plan_execute** | LLM + tool-agent plan → explain → execute |
| test | **job** | Async test run; poll or callback; returns report artifact |
| dev | **code_loop** | Plan files → write → test → self-correct (Gemini/LiteLLM) |
| marketing | **campaign_draft** | Read REQ → generate copy → optional video-agent clip |
| support | **retrieve_respond** | CRM + KB search → answer → escalate to new REQ |
| admin | **checklist** | Read policy + memory → approval/deny artifact |

#### 2.6.5 ui-test-agent run profiles

| Profile | Purpose | Trigger keywords |
|---------|---------|-------------------|
| `AUTH_FLOW` | Login / auth regression | auth, login, sign in |
| `RELEASE_GATE` | Pre-release full gate | release, gate, regression |
| `SMOKE` | Quick sanity | smoke, quick test |

Baseline modes (Qdrant): `compare` | `seed` | `promote`.

#### 2.6.6 video-agent pipeline modes

| Mode | Scope | Phase |
|------|-------|-------|
| **transcribe** | Whisper STT + semantic tags only | Phase 2 (Scribe) |
| **plan_edit** | ActionPlanner — clip keep/discard/quarantine | Phase 3 (Marketing) |
| **execute_edit** | ActionExecutor — physical clip routing | Phase 3 |
| **full_pipeline** | All 16 steps in `run_pipeline.py` | Marketing batch jobs only |

#### 2.6.7 LLM model routing (all agents)

| Setting | Source | Default |
|---------|--------|---------|
| Model | LiteLLM `litellm-config` ConfigMap | `deepseek/deepseek-chat`, Together Llama, Gemini |
| Vision | ui-test-agent | `together_ai/Qwen/Qwen2.5-VL-72B-Instruct` |
| DevOps kagent | `modelconfig-litellm.yaml` | `litellm-together` |
| Trace | Langfuse callbacks on LiteLLM | All agents via gateway metadata |

**Rule:** New agents use `LITELLM_BASE_URL` + `LITELLM_MASTER_KEY` from Vault — no raw API keys in agent code.

#### 2.6.8 Auth & caller audit modes

| Header / env | Purpose |
|--------------|---------|
| Keycloak JWT | Gateway `Authorization: Bearer` — user identity + roles |
| `X-Agent-Caller` | tool-agent REST audit (`kagent-ui`, `gateway`, `cursor-mcp`) |
| `TOOL_AGENT_CALLER` | MCP stdio/HTTP bridge |
| `PIPELINE_USER_ID` | video_pipeline multi-user file segregation |

### 2.7 UI strategy: three surfaces, one gateway

**Recommendation: three surfaces — not one, not one-UI-per-agent.**

| Surface | App | Audience | Primary job |
|---------|-----|----------|-------------|
| **Portal A** | `am-modern-ui` (Flutter) | B2B/SaaS **end users** | Product chat, widgets, white-label customer experience |
| **Portal B** | `ai-bots/frontend` (React, enhanced) | B2B workspace + internal teams | **All agents**, chat, **IntegrationsHub**, profile, integration summary |
| **Portal C** | **kagent UI** | SRE / local infra | K8s deep ops, cluster debugging, tool-agent MCP (power users) |

All three call the **same gateway and agents** where applicable. No duplicate agent logic per UI.

| Approach | Verdict | Why |
|----------|---------|-----|
| **One UI for everyone** | ❌ Avoid | Wrong UX + security for end users vs SRE |
| **Three surfaces + one gateway** | ✅ **Recommended** | Right tool per audience; shared backend |
| **kagent replaces Portal B** | ❌ Avoid | No meetings, integrations hub, or business agents |
| **Portal B replaces kagent** | ❌ Avoid | SRE lose native K8s tool cards; keep both |
| **Separate UI per agent** | ❌ Avoid | Training cost, duplicate routing |

#### Portal A — End user / B2B SaaS customer-facing

| Field | Detail |
|-------|--------|
| **App** | **am-modern-ui** (Flutter) — portfolio, trade, dashboard |
| **URL** | `app.yourcompany.com` / `app.asrax.in` |
| **Audience** | Your SaaS customer’s **end users** (or AM retail investors) |
| **Agents** | **finance** or customer **support/onboarding** agents only (gateway pinned) |
| **UX** | Simple chat + widgets — no agent picker, no integrations admin |
| **Auth** | Keycloak: `user`, `customer` |
| **SaaS** | White-label per tenant (logo, colors, enabled customer agents) |

#### Portal B — B2B workspace + internal (chat + integrations + profile)

| Field | Detail |
|-------|--------|
| **App** | **ai-bots/frontend** (React) — enhance, do not rewrite |
| **URL** | `workspace.yourcompany.com` / `workspace.{tenant}.com` (B2B SaaS) |
| **Audience** | **B2B customer org employees** + your internal teams (eng, product, marketing, support, admin) |
| **Agents** | All tenant-enabled: scribe, **dev (ai-bots API)**, test, marketing, support, admin; devops **light** via chat |
| **UX today** | `LLMTestPanel` → **Chat**; `IntegrationsHub` → **Integrations** |
| **UX Phase 2–4** | Requirements + Meetings tabs; **Profile** + **Integration summary** + **Company profile** (admin) |
| **Backend** | Gateway `/chat/stream` + ai-bots `/api/services/*` for connect/test/execute/status |
| **Auth** | Keycloak: tenant-scoped roles (`engineering`, `marketing`, `support`, `admin`, …) |
| **B2B SaaS** | White-label Portal B per tenant (Phase 5) — **this is the main product UI you sell** |

**Why ai-bots UI here:** IntegrationsHub, service registry, SSE activity stream, and conversation API already exist — this **is** the internal integration + chat layer.

#### Portal C — Local infra & SRE (kagent UI)

| Field | Detail |
|-------|--------|
| **App** | **kagent UI** (existing cluster install) |
| **URL** | `kagent.munish.org` / in-cluster |
| **Audience** | **SRE, platform, local infra** teams only |
| **Agents** | `am-infra-ops`, `am-k8s-ops` — K8s MCP + tool-agent MCP |
| **UX** | Native K8s tool cards, pod logs, events — best for cluster debugging |
| **Auth** | Cluster/network restricted; role `sre` |
| **Not for** | Meetings, Jira connect UI, marketing, end users |

**Rule:** kagent uses the **same** `am-infra-ops` prompt and MCPs as devops-agent. Portal B can invoke devops via gateway for **most** eng users; kagent stays for **deep infra** work.

> **Diagram (Draw.io):** [enterprise-agent-ecosystem.drawio](diagrams/enterprise-agent-ecosystem.drawio) (page **DevOps Dual Entry**)

#### B2B SaaS — which UI for agents, integrations, and profile?

When you **sell the agent platform to other companies**, split by **who logs in**:

| B2B role | UI | What they get |
|----------|-----|---------------|
| **Customer org employees** (eng, marketing, support, admin) | **Portal B** — `ai-bots/frontend` | **All tenant-enabled agents**, chat, **IntegrationsHub**, **user profile**, **integration summary**, company profile (admin) |
| **Customer org downstream end users** (optional — e.g. investor, shopper) | **Portal A** — `am-modern-ui` | **1–2 pinned agents** only (finance, support); simple chat + widgets; **no** Jira/GitHub admin |
| **Your own SRE / infra team** | **Portal C** — kagent | K8s deep ops only |

**Answer for “B2B agents + all user integration summary + profile” → Portal B (`ai-bots/frontend`), white-labeled per tenant in Phase 5.**

Portal B becomes the **B2B workspace product** you resell. Portal A is an **optional add-on** when the buyer also needs a narrow customer-facing app (Asrax finance today).

**Portal B B2B screens (build on ai-bots, do not duplicate in Flutter):**

| Screen | Source / phase | Content |
|--------|----------------|---------|
| **Chat** | `LLMTestPanel` → gateway (Phase 1) | All agents allowed for tenant + role |
| **Integrations** | `IntegrationsHub` + `/api/services/*` (exists) | Connect / disconnect Jira, GitHub, Confluence, Grafana, … |
| **Integration summary** | **New** dashboard tab (Phase 4) | Per-user + org-wide status from `/api/services/status`; last sync, errors, connected count |
| **User profile** | **New** Profile tab (Phase 4) | Keycloak identity, roles, prefs, personal connected services, agent usage summary |
| **Company profile** | **New** Admin tab (Phase 4) | Static company docs for Scribe RAG (mission, products, org) — feeds [§14.4](ENTERPRISE_AGENT_ECOSYSTEM.md#144-company-profile-data-how-agent-knows-the-company) |
| **Requirements / Meetings** | New tabs (Phase 2) | REQ board + MOM from scribe-agent + company-memory |

**Multi-tenant (Phase 5):** Same Portal B codebase; `tenant_id` from JWT scopes IntegrationsHub, profile, and enabled agents. Per-tenant branding (logo, colors, host `workspace.{customer}.com`).

**Portal A in B2B:** Only when the buyer resells a **simple front door** to *their* customers — not the full agent + integration hub.

#### Shared backend (no duplication)

> **Diagram (Draw.io):** [enterprise-agent-ecosystem.drawio](diagrams/enterprise-agent-ecosystem.drawio) (pages **Three Surfaces Overview**, **B2B Routing**)


| User question | Best surface |
|---------------|--------------|
| "Show my portfolio" | Portal A |
| "Connect Jira and summarize standup" | Portal B |
| "Fix issue #123 and open PR" | Portal B → ai-bots dev |
| "Show my connected integrations and profile" | Portal B — Integrations + Profile tabs |
| "Why is langfuse CrashLooping in am-ai?" | Portal B chat **or** Portal C kagent |
| "Get pod logs for headlamp -n infra" | Portal C kagent (fastest UX) |

#### Parallel entries (allowed, not full portals)

| Entry | Audience | Role |
|-------|----------|------|
| **IDE MCP stdio** | Developers | Cursor → tool-agent / gateway tools |
| **Streamlit video_pipeline** | Marketing batch | Phase out → video-agent via Portal B |

#### URL layout (recommended)

| Host | Surface |
|------|---------|
| `app.asrax.in` | Portal A — end users |
| `workspace.asrax.in` | Portal B — B2B workspace + ai-bots UI |
| `kagent.munish.org` | Portal C — SRE only |

Traefik + Keycloak enforce role → host access.

> **Diagram (Draw.io):** [enterprise-agent-ecosystem.drawio](diagrams/enterprise-agent-ecosystem.drawio) (page **URL RBAC**)

#### RBAC matrix

| Role | Portal A | Portal B | Portal C kagent |
|------|----------|----------|-----------------|
| `user` / customer | ✅ | ❌ | ❌ |
| `engineering` | optional | scribe, dev, test, devops chat | optional |
| `sre` | ❌ | devops chat | ✅ **primary** |
| `qa` | ❌ | test, scribe read | ❌ |
| `marketing` | ❌ | marketing, scribe | ❌ |
| `support` | ❌ | support, scribe read | ❌ |
| `admin` | ❌ | admin, all read | optional |

#### What changes from today

| Today | Target |
|-------|--------|
| Flutter → fin-agent direct | Portal A → gateway |
| ai-bots UI standalone dev tool | **Portal B** — enhance IntegrationsHub + gateway chat |
| kagent = only ops UI | **Portal C** for SRE; Portal B covers eng devops chat |
| am-dev-agent CLI | ai-bots API via Portal B + gateway |
| Streamlit video editor | video-agent via Portal B |

#### Phase alignment

| Phase | UI work |
|-------|---------|
| **0** | Keep kagent + am-infra-ops live (Portal C) |
| **1** | Portal A → gateway; Portal B: wire chat to gateway; keep IntegrationsHub on ai-bots API |
| **2** | Portal B: Requirements + Meetings tabs; kagent unchanged |
| **4** | Portal B: Profile + Integration summary + Company profile (admin); marketing/support artifacts; Portal A: optional white-label end-user slice |
| **5** | SSO all surfaces; deprecate direct fin-agent URL |

---

## 3. Complete agent catalog (detailed)

Master table of **every agent and capability** in the ecosystem — existing, planned, and frozen.

### 3.1 Summary matrix

> **Master diagram (Draw.io):** [enterprise-agent-ecosystem.drawio](diagrams/enterprise-agent-ecosystem.drawio) — page **Enterprise Master** (all agents, integrations, feature flows)

| ID | Name | Layer | Status | Port | Phase | Primary audience |
|----|------|-------|--------|------|-------|------------------|
| `scribe` | Scribe | L3 | Planned | 8150 | 2 | All teams |
| `finance` | Finance | L3 | **Live** | 8100 | 1 wire | End users, finance |
| `devops` | DevOps | L3 | Partial (kagent) | 8151 | 1 | Engineering, SRE |
| `test` | Test | L3 | **Live** | 8130 | 1 wire | Engineering, QA |
| `dev` | Dev | L3 | Partial (CLI) | 8152 | 3 | Engineering |
| `backend` | Backend Dev | L3 | Planned (extends dev) | 8152 | 3 | Backend engineers |
| `marketing` | Marketing | L3 | Planned | 8153 | 4 | Marketing |
| `support` | Support | L3 | Planned | 8154 | 4 | Support |
| `admin` | Admin | L3 | Planned | 8155 | 4 | Admin, compliance |
| `tool-agent` | Tool Agent | L4 | Built (deploy pending) | 8141 | 0 | Capability only |
| `video-agent` | Video Agent | L4 | Partial (Streamlit) | 8156 | 2–3 | Capability only |
| `company-memory` | Company Memory | L4 | Planned | 8157 | 2 | Capability only |
| `am-k8s-ops` | K8s Ops (kagent) | L3 alt | **Live** | kagent UI | 0 | SRE optional UI |
| `am-infra-ops` | Infra Ops (kagent) | L3 alt | Config ready | kagent UI | 0 | SRE optional UI |
| `db-agent` | DB Agent | L3 legacy | **Frozen** | 8140 | — | Deprecated |

---

### 3.2 L3 Domain agents

---

#### 3.2.1 Scribe (`scribe-agent`) — PLANNED · Phase 2

| Field | Detail |
|-------|--------|
| **Purpose** | Join meetings / accept uploads; extract requirements, decisions, action items into company memory |
| **Repo** | `am-agents/scribe-agent/` (new) |
| **Lifecycle phase** | Discovery → Requirements |
| **Stack** | FastAPI, LangGraph, LiteLLM |
| **Workflow mode** | `extract` — no destructive actions |
| **Capabilities used** | company-memory (write), video-agent (`transcribe`), jira MCP (sync out, Phase 3) |
| **API** | `POST /api/v1/agent/chat/stream`, `POST /api/v1/ingest/transcript`, `POST /api/v1/ingest/audio` |
| **Output artifacts** | `requirement_list`, `meeting_summary`, `decision_log` |
| **Memory writes** | `meetings`, `requirements`, `decisions`, `action_items` |
| **Example prompts** | "Summarize today's standup", "What did we decide about ETF launch?", "Create requirements from this transcript" |
| **RBAC roles** | `all` (read); `engineering`, `product` (write) |
| **Reuse** | Whisper/LLM from `ai-video-editor/.../tagging.py` via video-agent |
| **Do not duplicate** | Full video pipeline in Scribe; local dev-agent requirement folders |

**Meeting platform integration:** See [§14 Meeting agent integration](#14-meeting-agent-integration-zoho-google-meet-teams) for Zoho / Google Meet / Teams join, live Q&A on company profile, MOM, and task creation.

---

#### 3.2.2 Finance (`fin-agent`) — LIVE · Phase 1 wire

| Field | Detail |
|-------|--------|
| **Purpose** | Portfolio, holdings, trades, analysis — end-user finance assistant with Flutter widgets |
| **Repo** | `am-fin-agent/` |
| **Lifecycle phase** | Product / end-user (parallel to enterprise lifecycle) |
| **Stack** | FastAPI, LangGraph ReAct, MongoDB, am-analysis API |
| **Workflow mode** | `ReAct + widget` — parallel tool calls, circuit breaker 5s |
| **LLM** | Together/Gemini via agent config → migrate to LiteLLM |
| **API today** | `POST /api/v1/ai/chat`, `GET /api/v1/ai/stream/{sessionId}` |
| **Gateway route** | Keywords: portfolio, holdings, pnl, trade, sector, movers |
| **Tools (registered)** | |

**Tools:**

| Tool | Data source | Widget mapping |
|------|-------------|----------------|
| `get_portfolio_summary` | MongoDB | `PORTFOLIO_SUMMARY` |
| `get_holdings_list` | MongoDB | `HOLDINGS_TABLE` |
| `get_holding_details` | MongoDB | `HOLDINGS_TABLE` |
| `get_benchmark_comparison` | MongoDB | `TEXT_RESPONSE` |
| `get_top_movers` | am-analysis | `TOP_MOVERS` |
| `get_sector_allocation` | am-analysis | `ALLOCATION_PIE_CHART` |
| `analyze_etf_overlap` | am-analysis | `TEXT_RESPONSE` |
| `get_fund_details` | am-analysis | `TEXT_RESPONSE` |
| `get_recent_activity` | MongoDB | `RECENT_ACTIVITY` |
| `get_trade_history` | MongoDB | `TEXT_RESPONSE` |

| **Session** | In-memory (20 msgs) → Redis in Phase 5 |
| **UI today** | Flutter `am_ai_ui` → fin-agent **direct** (migrate to gateway Phase 1) |
| **Company memory** | Not used (end-user product scope) |
| **Do not duplicate** | Portfolio tools in gateway or other agents |

---

#### 3.2.3 DevOps (`devops-agent`) — PARTIAL · Phase 1

| Field | Detail |
|-------|--------|
| **Purpose** | K8s inspection + infra data store queries (mongo, kafka, vault, grafana, …) |
| **Repo** | `am-agents/devops-agent/` (new thin wrapper) |
| **Template** | Copy prompt + tool list from [`agent-am-infra-ops.yaml`](../k8s/kagent/agent-am-infra-ops.yaml) |
| **Lifecycle phase** | Test → Release / incident response |
| **Stack** | FastAPI + LiteLLM ReAct OR kagent-compatible MCP client |
| **Workflow mode** | `plan_execute` — mandatory for tool-agent backends |
| **Capabilities** | tool-agent MCP, k8s MCP (kagent-tool-server) |
| **K8s tools** | `k8s_get_resources`, `k8s_describe_resource`, `k8s_get_pod_logs`, `k8s_get_events`, `k8s_get_available_api_resources` |
| **tool-agent tools** | `tool_agent_plan`, `tool_agent_execute`, `tool_agent_list_backends`, `tool_agent_health`, `tool_agent_ready` |
| **API** | `POST /api/v1/agent/chat/stream` |
| **Output artifacts** | `markdown`, `k8s_table`, `infra_query_result` |
| **Memory writes** | `lifecycle_events` on deploy confirm (Phase 3) |
| **Example prompts** | "Pods not Running in am-ai", "Consumer lag on kafka topic X", "Vault path for litellm secrets" |
| **RBAC roles** | `engineering`, `sre` |
| **kagent parallel** | `am-infra-ops` in kagent UI — same brain, optional SRE entry |
| **Do not duplicate** | Embedded mongo/kafka clients; db-agent; second K8s agent logic |

---

#### 3.2.4 Test (`ui-test-agent`) — LIVE · Phase 1 wire

| Field | Detail |
|-------|--------|
| **Purpose** | Autonomous Playwright UI testing with vision (Qwen VL) |
| **Repo** | `am-agents/ui-test-agent/` |
| **Lifecycle phase** | Development → Test |
| **Stack** | FastAPI, LangGraph, Playwright, LiteLLM, Qdrant baselines |
| **Workflow mode** | `job` — async run + poll + report artifact |
| **API** | `POST /api/v1/test/run`, `POST /api/v1/test/run-auth`, `GET /api/v1/test/{testId}` |
| **Gateway proxy** | `am-mcp-gateway/app/api/ui_test_tools.py` — `run_modern_ui_auth_test` |
| **Run profiles** | `AUTH_FLOW`, `RELEASE_GATE`, `SMOKE` |
| **LLM routing** | `direct` or `gateway` → LiteLLM; planner + vision models configurable |
| **Output artifacts** | HTML report URL, `test_report`, pass/fail status |
| **Memory linking** | `requirementId` param (Phase 3) → update REQ status `tested` |
| **Scheduler** | Nightly regression stub (2 AM cron in `main.py`) |
| **Example prompts** | "Run auth smoke on preprod", "Regression test portfolio UI" |
| **RBAC roles** | `engineering`, `qa` |
| **Capabilities** | tool-agent (optional infra checks during test failures) |
| **Do not duplicate** | Second Playwright runner; am-ui-test-agent legacy root |

---

#### 3.2.5 Dev (`dev-agent`) — PARTIAL (CLI) · Phase 3 HTTP

| Field | Detail |
|-------|--------|
| **Purpose** | Implement features, fix bugs, scaffold projects from requirements |
| **Repo** | `am-dev-agent/` → `am-agents/dev-agent/` (monorepo target) |
| **Lifecycle phase** | Requirements → Development |
| **Stack** | CLI today; FastAPI Phase 3; Gemini today → LiteLLM |
| **Workflow mode** | `code_loop` — plan → write → verify → self-correct |
| **CLI commands** | `am-dev init`, `am-dev run`, `--feature`, `--requirement`, `--dry-run` |
| **Prompt roles** | architect, developer, qa_engineer, tech_lead, reviewer, researcher |
| **Tech stacks** | Python, Spring Boot, React, Flutter templates |
| **API (planned)** | `POST /api/v1/dev/run` with `{ requirementId, repo, task, dryRun }` |
| **Capabilities** | github MCP (PR link), company-memory (read REQ) |
| **Memory writes** | `lifecycle_events` — PR URL, status `in_progress` → `dev_done` |
| **Example prompts** | "Implement REQ-001 auth endpoint", "Add healthcheck to portfolio-api" |
| **RBAC roles** | `engineering` |
| **Do not duplicate** | New coding agent; local `requirements/` as source of truth |

---

#### 3.2.6 Backend Dev (`backend`) — PLANNED · Phase 3 (extends dev)

| Field | Detail |
|-------|--------|
| **Purpose** | API design, microservice schemas, postgres/kafka inspection for backend work |
| **Implementation** | Same `dev-agent` HTTP service with `persona=backend` or separate registry entry |
| **Workflow mode** | `code_loop` + `plan_execute` for infra reads |
| **Capabilities** | github MCP, tool-agent (postgres, kafka read-only), company-memory |
| **Example prompts** | "Design OpenAPI for ETF holdings", "Show postgres schema for portfolio" |
| **RBAC roles** | `engineering` |
| **Do not duplicate** | Separate backend codebase; embed postgres client |

---

#### 3.2.7 Marketing (`marketing-agent`) — PLANNED · Phase 4

| Field | Detail |
|-------|--------|
| **Purpose** | Launch campaigns, landing copy, email drafts, social clips from requirements |
| **Repo** | `am-agents/marketing-agent/` (new) |
| **Lifecycle phase** | Release → Marketing |
| **Stack** | FastAPI, LangGraph, LiteLLM |
| **Workflow mode** | `campaign_draft` |
| **Capabilities** | company-memory (read launch REQs), video-agent (clip generation), analytics MCP (Phase 4+) |
| **Output artifacts** | `campaign_preview`, `email_draft`, `video_clip`, `landing_copy` |
| **Memory reads** | Requirements with `owner_agent=marketing` or launch tags |
| **Example prompts** | "Draft email for ETF launch March 1", "Create 60s product clip from demo recording" |
| **RBAC roles** | `marketing` |
| **Reuse** | video-agent plan/execute for clips — not raw FFmpeg in agent |
| **Do not duplicate** | Streamlit video UI as enterprise entry |

---

#### 3.2.8 Support (`support-agent`) — PLANNED · Phase 4

| Field | Detail |
|-------|--------|
| **Purpose** | Customer tickets, FAQ, escalations with product context from company memory |
| **Repo** | `am-agents/support-agent/` (new) |
| **Lifecycle phase** | Release → Support → Feedback loop |
| **Stack** | FastAPI, LangGraph, LiteLLM |
| **Workflow mode** | `retrieve_respond` |
| **Capabilities** | CRM MCP (Zendesk/Intercom/custom), company-memory (REQ + FAQ), kb MCP |
| **Output artifacts** | `ticket_card`, `faq_suggestion`, `escalation_req` |
| **Memory writes** | New REQ on escalation; link ticket → requirement |
| **Example prompts** | "Answer ETF fee question", "Escalate login bug — create REQ" |
| **RBAC roles** | `support` |
| **Feedback loop** | Escalation → Scribe updates memory → dev agent |
| **Do not duplicate** | Product context stored only in CRM |

---

#### 3.2.9 Admin (`admin-agent`) — PLANNED · Phase 4

| Field | Detail |
|-------|--------|
| **Purpose** | Access requests, compliance checklists, finance ops (non-portfolio), HR workflows |
| **Repo** | `am-agents/admin-agent/` (new) |
| **Lifecycle phase** | Admin / governance (cross-cutting) |
| **Stack** | FastAPI, LangGraph, LiteLLM |
| **Workflow mode** | `checklist` |
| **Capabilities** | company-memory, access-management MCP (TBD) |
| **Output artifacts** | `approval_request`, `compliance_checklist`, `access_grant` |
| **Scope note** | Distinct from **fin-agent** (end-user portfolio) — admin is internal ops |
| **Example prompts** | "Approve vault access for new engineer", "Compliance checklist for ETF launch" |
| **RBAC roles** | `admin` |
| **Do not duplicate** | Extending fin-agent for admin; separate admin tools in gateway |

---

#### 3.2.10 K8s Ops (`am-k8s-ops`) — LIVE · kagent only

| Field | Detail |
|-------|--------|
| **Purpose** | Read-only Kubernetes ops (pods, logs, events) — no infra data stores |
| **Config** | [`agent-k8s-ops.yaml`](../k8s/kagent/agent-k8s-ops.yaml) |
| **UI** | kagent UI only (`kagent.munish.org`) |
| **Tools** | k8s MCP only |
| **Enterprise path** | Superseded by `devops-agent` for unified UI; keep for SRE power users |
| **Do not duplicate** | Third DevOps implementation in gateway |

---

#### 3.2.11 Infra Ops (`am-infra-ops`) — CONFIG READY · kagent + devops-agent template

| Field | Detail |
|-------|--------|
| **Purpose** | K8s + tool-agent unified ops — **canonical DevOps prompt** |
| **Config** | [`agent-am-infra-ops.yaml`](../k8s/kagent/agent-am-infra-ops.yaml) |
| **Enterprise mapping** | `devops-agent` copies this prompt verbatim |
| **MCP servers** | `kagent-tool-server`, `am-tool-agent-mcp` |
| **Phase 0** | Deploy with tool-agent MCP manifests |

---

#### 3.2.12 DB Agent (`db-agent`) — FROZEN

| Field | Detail |
|-------|--------|
| **Purpose** | Legacy NL→DB — superseded by tool-agent |
| **Repo** | `am-agents/db-agent/` |
| **Port** | 8140, ingress `/db` |
| **Policy** | **No new features.** CI check `check-db-agent-untouched.sh` |
| **Migration** | All infra NL queries → tool-agent :8141 |

---

### 3.3 L4 Capabilities (not user-facing agents)

---

#### 3.3.1 Tool Agent (`tool-agent`) — BUILT · Phase 0 deploy

| Field | Detail |
|-------|--------|
| **Purpose** | Headless NL→safe infra operations across 7 backends |
| **Repo** | `am-agents/tool-agent/` |
| **Port** | 8141 · ingress `/tools` · preprod `https://am.asrax.in/tools` |
| **Layer** | L4 only — no LLM personality for outer MCP consumers |
| **Backends** | mongo, postgres, redis, kafka, qdrant, grafana, vault |
| **API** | `POST /api/v1/tools/plan`, `/execute`, `/query` + `/stream` variants |
| **MCP** | stdio bridge (IDE), HTTP server (kagent RemoteMCPServer) |
| **Dynamic catalog** | TTL cache for vault paths, kafka topics; convention + fuzzy resolve |
| **Modes** | plan, execute, query (IDE only), MCP stream |
| **Tests** | 91 pytest, 24/24 query corpus |
| **Consumers** | devops-agent, am-infra-ops, IDE Cursor, test-agent (optional) |
| **Contract** | [`MCP_CONTRACT.md`](../tool-agent/docs/MCP_CONTRACT.md) v1.0.0 |

---

#### 3.3.2 Video Agent (`video-agent`) — PARTIAL · Phase 2–3 wrap

| Field | Detail |
|-------|--------|
| **Purpose** | Transcription, semantic tagging, video clip plan/execute |
| **Source** | `ai-video-editor/video_pipeline/` |
| **Port** | 8156 (planned HTTP wrapper) |
| **Today** | Streamlit `app.py` + CLI `run_pipeline.py` — **not** enterprise UI |
| **7-layer model** | Perception → Scoring → Judgment → Analytics → Planning → Execution → Explanation |
| **Key modules** | `tagging.py` (Whisper+LLM), `planner.py`, `executor.py`, `explainer.py` |
| **Planned MCP tools** | `video_transcribe`, `video_plan_edit`, `video_execute`, `video_health` |
| **State** | MongoDB or JSON per `PIPELINE_USER_ID` |
| **Consumers** | scribe-agent (transcribe), marketing-agent (clips) |
| **Do not duplicate** | Second Whisper integration in Scribe |

---

#### 3.3.3 Company Memory (`company-memory`) — PLANNED · Phase 2

| Field | Detail |
|-------|--------|
| **Purpose** | Single source of truth for requirements, meetings, lifecycle |
| **Store** | Postgres (authoritative) + Qdrant (semantic search) |
| **Port** | 8157 |
| **Planned MCP tools** | `memory_search`, `memory_get_requirement`, `memory_update_status`, `memory_link_artifact` |
| **Consumers** | All L3 agents |
| **Sync out** | Jira/Linear MCP (tickets are copies, not primary) |

---

#### 3.3.4 Satellite MCPs

| MCP | Tools (planned) | Consumers | Phase |
|-----|-----------------|-----------|-------|
| **k8s** | `k8s_get_*` | devops, am-k8s-ops | 0 (live) |
| **vault** | vault read paths | kagent | 0 (live) |
| **grafana** | dashboard/query | kagent | 0 (live) |
| **github** | `search_code`, `create_pr`, `get_pr` | dev, backend | 3 |
| **jira** | `create_issue`, `link_issue` | scribe, dev, support | 3 |
| **slack** | `post_message`, `read_thread` | scribe intake | 2–3 |
| **crm** | `get_ticket`, `create_ticket` | support | 4 |
| **analytics** | campaign metrics | marketing | 4 |

---

### 3.4 Agent ↔ capability dependency map

> **Diagram (Draw.io):** [enterprise-agent-ecosystem.drawio](diagrams/enterprise-agent-ecosystem.drawio) (page **Repo Reuse**)


---

### 3.5 Agent ↔ lifecycle phase map

| Lifecycle phase | Primary agent | Secondary | Memory update |
|---------------|---------------|-----------|---------------|
| Discovery | scribe | — | meetings, requirements |
| Requirements approval | scribe / human | admin | status → approved |
| Development | dev, backend | — | in_progress, PR link |
| Test | test | devops (infra debug) | tested / failed |
| Release | devops | admin | released |
| Marketing | marketing | video-agent | — |
| Support | support | scribe (escalation) | supported, new REQ |
| Admin / governance | admin | — | compliance events |
| End-user product | finance | — | (out of enterprise memory scope) |

---

## 4. Inventory — what exists today

| Asset | Location | Reuse in plan | Do not duplicate |
|-------|----------|---------------|------------------|
| Gateway + finance route | `am-platform/am-mcp-gateway` | Extend router | New gateway |
| fin-agent + widgets | `am-fin-agent` | L3 finance | Portfolio tools in gateway |
| tool-agent | `am-agents/tool-agent` | L4 infra | db-agent, per-agent DB clients |
| ui-test-agent | `am-agents/ui-test-agent` | L3 test | New test runner |
| dev-agent CLI | `am-dev-agent` | Wrap as L3 HTTP | New coding agent |
| am-infra-ops | `k8s/kagent/agent-am-infra-ops.yaml` | DevOps prompt + tools | Second DevOps implementation |
| kagent UI | `kagent.munish.org` | SRE optional UI | Third enterprise UI |
| Flutter ai-chat | `am-modern-ui/am_ai_ui` | L1 shell | Direct fin-agent forever |
| video_pipeline | `ai-video-editor/video_pipeline` | L4 video-agent + Scribe STT | Streamlit as enterprise UI |
| LiteLLM, Langfuse, Vault, Keycloak | cluster | All agents | Direct LLM keys per agent |
| db-agent | `am-agents/db-agent` | **Frozen** | Any new work |
| **ai-bots** | `ai-bots/` | **Dev agent + Integration API + RAG** — see §4.1 | Rebuilding dev-agent HTTP, Jira/GitHub layer, integration UI |

**Readiness:** ~55% with ai-bots counted (was ~45% without).

### 4.1 ai-bots — deep reuse map (avoid duplicate work)

[`ai-bots/`](../../ai-bots/) is a **partial enterprise platform already built** — closer to SaaS backend + dev-agent than anything in `am-agents/` except tool-agent. Treat it as **canonical dev-agent + integration layer**, not a throwaway prototype.

#### What ai-bots already has

| Capability | Location | Enterprise role |
|------------|----------|-----------------|
| **FastAPI platform API** | `interfaces/http_api.py` `:5000` | Portal B backend prototype |
| **OpenAPI spec** | `openapi.json` | SaaS API contract starting point |
| **Integration connect API** | `/api/services/connect`, `/disconnect`, `/status`, `/execute` | **Exactly the “Integration API” the plan said was missing** |
| **Chat + sessions** | `/api/chat/conversations`, messages CRUD | Extend → gateway sessions |
| **SSE orchestration stream** | `POST /api/orchestration/stream` | Same pattern as gateway unified SSE |
| **LangGraph pipeline** | `orchestration/facade.py` | parse → enrich → prompt → execute |
| **GitHub client** | `shared/clients/github_client.py` | dev-agent, scribe task sync |
| **Jira client** | `shared/clients/jira_client.py` | scribe action items → tickets |
| **Confluence client** | `shared/clients/confluence_client.py` | MOM/docs publish, company profile RAG |
| **Grafana client** | `shared/clients/grafana_client.py` | Overlap with tool-agent — **use tool-agent for infra NL; keep ai-bots for alert webhooks** |
| **Teams bot** | `interfaces/teams_bot.py` | Partial Teams entry (commands, not full meeting bot) |
| **Webhooks** | `/api/webhook/{source}` | github, jira, grafana, teams |
| **Doc orchestrator** | `/api/docs/orchestrate` | analyze → GitHub commit → Confluence → **Jira ticket** |
| **Issue → PR workflow** | `features/*` analyze, code_gen, test_orchestrator | dev-agent lifecycle |
| **Vector DB / RAG** | `shared/vector_db/` Qdrant, Chroma, repo indexer | Company profile RAG for scribe |
| **LLM factory** | Together + Azure + resilient orchestrator | Migrate calls to LiteLLM; keep factory pattern |
| **React frontend** | `frontend/` IntegrationsHub, SSE panels | **UX reference** for Portal B integrations settings |
| **SQLAlchemy DB** | issues, analyses, fixes, chat | Extend schema → requirements/meetings OR migrate to company-memory |
| **Observability** | Prometheus + OpenTelemetry | Align with Langfuse at gateway |

#### Map ai-bots → enterprise agents (reuse, don’t rebuild)

| Enterprise agent | ai-bots reuse | am-agents / other | Decision |
|------------------|---------------|-------------------|----------|
| **dev-agent** | **PRIMARY** — full API + orchestration | `am-dev-agent` CLI → **deprecate/wrap** | Gateway `dev` route → **ai-bots** `:5000` |
| **backend-dev** | Same ai-bots, `backend` persona in router | — | One service, two registry entries |
| **scribe** | vector_db, Jira ticket from doc_orchestrator | **NEW** meeting/MOM modules | Scribe = new agent **calling** ai-bots integrations |
| **devops** | Grafana webhook only | **tool-agent** + devops-wrapper | **Do not** duplicate infra queries in ai-bots MongoDB |
| **test** | test_orchestrator feature (partial) | **ui-test-agent** Playwright | Keep ui-test-agent for UI; ai-bots for unit test gen only |
| **marketing** | doc_generator, Confluence publish | video-agent | Partial |
| **support** | — | **NEW** | ai-bots Jira/Confluence as capabilities |
| **Integration API** | **`/api/services/*`** | gateway proxies or merges | **Do not build second connect API** |
| **SaaS UI integrations panel** | `IntegrationsHub.tsx` patterns | Portal B new app | Port UI patterns, tenant-scope API |

#### Revised architecture (with ai-bots)

> **Diagram (Draw.io):** [enterprise-agent-ecosystem.drawio](diagrams/enterprise-agent-ecosystem.drawio) (pages **Three Surfaces Overview**, **Repo Reuse**)


#### What ai-bots does NOT replace (still build in am-agents)

| Gap | Still needed |
|-----|--------------|
| Meeting join / MOM / requirements board | **scribe-agent** + **company-memory** |
| Infra NL (mongo, kafka, vault) | **tool-agent** only |
| Multi-agent gateway router | **Extend am-mcp-gateway** |
| Multi-tenant SaaS | `tenant_id` on gateway + memory + ai-bots services |
| End-user finance | **fin-agent** + am-modern-ui |
| Playwright UI testing | **ui-test-agent** |
| Keycloak RBAC | Wire gateway; ai-bots auth is dev-era |

#### Duplicate work to **stop** in the plan

| Planned item | Use instead |
|--------------|-------------|
| Phase 3 “dev-agent HTTP API” greenfield | **ai-bots** already has HTTP + OpenAPI |
| Phase 3 “GitHub MCP satellite” from scratch | ai-bots GitHub client → wrap as MCP **or** proxy existing API |
| Phase 3 “Jira MCP” from scratch | ai-bots Jira + `DocOrchestrationRequest.create_jira_ticket` |
| New integration connect UI from zero | Fork **IntegrationsHub** from ai-bots React |
| Second vector/RAG stack for company profile | **ai-bots vector_db** + Qdrant provider |
| am-dev-agent CLI as long-term dev path | ai-bots API behind gateway |

#### Migration path (no big-bang rewrite)

1. **Phase 1:** Register ai-bots in `agents.yaml` as `dev` agent; gateway proxies `/api/orchestration/stream`  
2. **Phase 2:** Add scribe-agent; call ai-bots `/api/services` for Jira + vector_db for RAG  
3. **Phase 2:** Extend ai-bots DB **or** company-memory Postgres — pick **one** store for requirements (prefer company-memory; ai-bots keeps issues/PRs)  
4. **Phase 3:** Point LiteLLM at ai-bots LLM calls; Langfuse at gateway  
5. **Phase 5:** Multi-tenant: add `tenant_id` to ServiceManager + gateway JWT  

**References:** [`ai-bots/README.md`](../../ai-bots/README.md), [`ai-bots/orchestration/README.md`](../../ai-bots/orchestration/README.md), [`ai-bots/openapi.json`](../../ai-bots/openapi.json)

---

## 5. Anti-duplication charter

Before any PR, answer:

| # | Question | Wrong answer → duplicate |
|---|----------|--------------------------|
| 1 | Which layer (L1–L4)? | Feature in wrong layer |
| 2 | Does this already exist? | Second infra agent, second router |
| 3 | Tool or agent? | LLM in capability layer |
| 4 | Goes through gateway? | UI → agent direct |
| 5 | Uses company memory? | Local requirements/ folders |
| 6 | Uses LiteLLM? | Direct Together/Gemini in new code |
| 7 | Needs own UI? | New Streamlit/kagent for each domain |

**Frozen / deprecated:**

- `db-agent` — no changes
- `am-ui-test-agent` (legacy root) — use `am-agents/ui-test-agent`
- Direct `Together` in new agents — use LiteLLM
- Second requirements store without memory sync

---

## 6. Integration map (how it works end-to-end)

### 6.1 User chat flow

> **Diagram (Draw.io):** [enterprise-agent-ecosystem.drawio](diagrams/enterprise-agent-ecosystem.drawio) (page **Chat Flow**)


### 6.2 Meeting → release lifecycle

> **Diagram (Draw.io):** [enterprise-agent-ecosystem.drawio](diagrams/enterprise-agent-ecosystem.drawio) (pages **Phases**, **Portal B Screens**)


### 6.3 Parallel entry points (allowed, not duplicates)

| Entry | Audience | Path |
|-------|----------|------|
| Enterprise UI | All employees | UI → gateway → L3 → L4 |
| IDE MCP stdio | Developers | Cursor → tool-agent / gateway tools |
| kagent UI | SRE power users | kagent → same MCPs as devops-agent |
| Flutter portfolio | End users | Can stay fin-agent direct OR gateway `agent=finance` |

---

## 7. Phased execution plan (no duplicate work)

Each phase **only builds net-new** or **extends** — never replaces working code with a parallel implementation.

---

### Phase 0 — Platform unblock (Week 1–2)

**Goal:** Shared capabilities live on preprod. Zero new agents.

| # | Task | Repo | Integration | Avoids |
|---|------|------|-------------|--------|
| 0.1 | Deploy tool-agent image | `am-agents/tool-agent` | Ingress `/tools`, Helm preprod | db-agent queries |
| 0.2 | Apply kagent MCP manifests | `am-agents/k8s/kagent` | am-infra-ops, RemoteMCPServer | New K8s tooling |
| 0.3 | Smoke tool-agent corpus | scripts | `--preprod` 24/24 | — |
| 0.4 | Add `agents.yaml` schema | `am-mcp-gateway` | Doc only | Hardcoded routes |
| 0.5 | Freeze db-agent | policy | CI check | Duplicate infra agent |

**Exit:** `am-infra-ops` works in kagent; `https://am.asrax.in/tools/health` OK.

**Execution commands (when VPS reachable):**

```bash
kubectl apply -f am-agents/k8s/kagent/tool-agent-mcp-deployment.yaml
kubectl apply -f am-agents/k8s/kagent/remote-mcpserver-tool-agent.yaml
kubectl apply -f am-agents/k8s/kagent/agent-am-infra-ops.yaml
```

---

### Phase 1 — One router, wire existing agents (Week 3–5)

**Goal:** Gateway routes to agents that **already exist**. No new domain logic.

| # | Task | Repo | Details | Avoids |
|---|------|------|---------|--------|
| 1.1 | Agent registry loader | `am-mcp-gateway` | Load `agents.yaml`, validate | Per-agent if/else in chat.py |
| 1.2 | Intent router | `am-mcp-gateway` | Keywords + optional LLM classify | Multiple routers |
| 1.3 | Unified SSE emitter | `am-mcp-gateway` | Normalized event types | Per-agent SSE formats |
| 1.4 | Finance route | gateway → fin-agent | Existing client, add SSE passthrough | Rewriting fin-agent |
| 1.5 | Test route | gateway → ui-test-agent | Reuse `ui_test_tools.py` patterns | New test agent |
| 1.6 | DevOps-agent wrapper | **new thin service** | HTTP facade: same prompt as am-infra-ops, calls tool-agent MCP + k8s MCP | Reimplementing k8s logic |
| 1.7 | Flutter → gateway | `am-modern-ui/am_ai_ui` | `AiChatService` base URL → gateway | Permanent fin bypass |
| 1.8 | Agent badge in UI | `am-modern-ui` | Show `agent_selected` event | — |
| 1.9 | Langfuse metadata | gateway | `agentId`, `sessionId` on all traces | — |

**DevOps wrapper design (no duplicate of am-infra-ops):**

```
devops-agent (8151) = HTTP adapter
  ├── system prompt: copy from agent-am-infra-ops.yaml
  ├── tools: HTTP to tool-agent /api/v1/tools/plan|execute
  └── tools: MCP proxy to kagent-tool-server (or reuse mcp_http_server pattern)
```

**Exit:** Single Flutter chat reaches finance, devops, test via gateway SSE.

**Tests:**

- Postman: gateway `/api/v1/chat/stream` × 3 agent intents
- Flutter: portfolio question → finance widget; pod question → devops markdown

---

### Phase 2 — Company memory + Scribe MVP (Week 6–9)

**Goal:** Requirements captured once, used everywhere. Manual intake first.

| # | Task | Repo | Details | Avoids |
|---|------|------|---------|--------|
| 2.1 | Company memory API | `am-platform/company-memory` or gateway module | Postgres CRUD + REST | Scattered Notion/docs |
| 2.2 | Qdrant indexer | memory service | Embed requirements + transcripts | — |
| 2.3 | scribe-agent | `am-agents/scribe-agent` | LangGraph: transcript → REQ/decisions/actions | Building STT from scratch |
| 2.4 | Extract STT module | from `ai-video-editor/.../tagging.py` | Shared lib or video-agent call | Duplicate Whisper integration |
| 2.5 | video-agent HTTP wrapper | `ai-video-editor` or `am-agents/video-agent` | `POST /transcribe` only (Phase 2 scope) | Full pipeline in Scribe |
| 2.6 | Gateway scribe route | gateway | Registry entry | — |
| 2.7 | Requirements board UI | `am-modern-ui` | List/filter/link to chat | Second requirements UI |
| 2.8 | Manual upload UI | `am-modern-ui` | Paste transcript / upload audio | — |
| 2.9 | Memory MCP tools | memory service | `memory_*` for other agents | Agents querying Postgres direct |

**Exit:** Paste standup notes → REQ-001..N in board → open dev chat with REQ context.

**Reuse from ai-video-editor:**

- Whisper + LLM semantic extraction from `tagging.py`
- plan/execute/explain **pattern** (not clip-specific logic)

---

### Phase 3 — Lifecycle linking (Week 10–13)

**Goal:** REQ flows dev → test → release with traceability.

| # | Task | Repo | Details | Avoids |
|---|------|------|---------|--------|
| 3.1 | dev-agent HTTP API | `am-dev-agent` | `POST /run` + `requirementId`; read memory not local files | New dev agent |
| 3.2 | Gateway dev route | gateway | Registry | — |
| 3.3 | GitHub MCP | capability satellite | PR link → memory | Git logic in dev-agent |
| 3.4 | Jira/Linear MCP | capability | Scribe action items → tickets (sync out) | Jira as primary store |
| 3.5 | ui-test-agent linking | `ui-test-agent` | `requirementId` param; post pass/fail to memory | Duplicate test tracking |
| 3.6 | DevOps release hook | devops-agent | Mark `released` on deploy confirm | — |
| 3.7 | Meeting bot v1 | scribe-agent | One platform (Teams OR Meet) | All platforms at once |
| 3.8 | Cross-agent handoff | gateway | `workingSummary` in session Redis | Re-explaining in each agent |
| 3.9 | video-agent full wrap | video-agent | plan/execute edit for marketing clips | Streamlit enterprise UI |

**Exit:** REQ-001 visible through dev → test → devops on requirements board with artifact links.

---

### Phase 4 — Business ops agents (Week 14–19)

**Goal:** Marketing, support, admin on same spine.

| # | Task | Repo | Capabilities | Avoids |
|---|------|------|--------------|--------|
| 4.1 | marketing-agent | `am-agents/marketing-agent` | memory, video-agent, analytics MCP | Video pipeline in agent |
| 4.2 | support-agent | `am-agents/support-agent` | memory, CRM MCP, KB | Duplicate product context |
| 4.3 | admin-agent | `am-agents/admin-agent` | memory, access/compliance tools | Extending fin-agent for admin |
| 4.4 | Gateway routes + RBAC | gateway | Role → agent filter | — |
| 4.5 | Artifact widgets | `am-modern-ui` | ticket, campaign, approval cards | — |
| 4.6 | Feedback loop | scribe + support | Escalation → new REQ in memory | Orphan tickets |

**Exit:** Launch campaign + support FAQ from same REQ object Scribe created.

---

### Phase 5 — Enterprise hardening (Week 20+)

| # | Task | Details |
|---|------|---------|
| 5.1 | Redis sessions | Replace fin-agent in-memory store; gateway session ownership |
| 5.2 | RBAC per tool | Keycloak roles → agent + capability permissions |
| 5.3 | LiteLLM MCP hub | Register gateway + capability MCPs centrally |
| 5.4 | Eval corpora | Per-agent YAML corpora (like tool-agent) in CI |
| 5.5 | OpenAPI export | `docs/MCP_CONTRACT.md` pattern for all capabilities |
| 5.6 | Deprecate direct paths | Remove Flutter → fin direct; document IDE MCP only |
| 5.7 | HA / rate limits | Gateway circuit breakers (pattern exists in fin-agent) |

---

## 8. Phase dependency graph

> **Diagram (Draw.io):** [enterprise-agent-ecosystem.drawio](diagrams/enterprise-agent-ecosystem.drawio) (page **Phases**)


| Phase | Weeks | New packages | Extends | Net-new agents |
|-------|-------|--------------|---------|----------------|
| 0 | 1–2 | 0 | tool-agent deploy, kagent | 0 |
| 1 | 2–3 | devops-agent wrapper | gateway, Flutter | 0 (wrapper only) |
| 2 | 3–4 | company-memory, scribe-agent, video-agent/transcribe | gateway, Flutter, ai-video-editor | scribe |
| 3 | 3–4 | github/jira MCP | dev-agent HTTP, ui-test, video-agent | 0 |
| 4 | 4–6 | marketing, support, admin | gateway, Flutter | 3 |
| 5 | ongoing | — | all | 0 |

---

## 9. Repository & deployment layout

```text
AM-Portfolio-grp/
├── am-platform/
│   ├── am-mcp-gateway/          # L2 — extend (registry, router, SSE)
│   └── company-memory/          # NEW Phase 2 — or gateway submodule first
├── am-agents/
│   ├── tool-agent/              # L4 — deploy Phase 0
│   ├── ui-test-agent/           # L3 test
│   ├── scribe-agent/            # NEW Phase 2
│   ├── video-agent/             # NEW Phase 2 — thin HTTP over video_pipeline
│   ├── devops-agent/            # NEW Phase 1 — thin wrapper
│   ├── marketing-agent/         # NEW Phase 4
│   ├── support-agent/           # NEW Phase 4
│   ├── admin-agent/             # NEW Phase 4
│   ├── db-agent/                # FROZEN
│   └── k8s/kagent/              # Phase 0 manifests
├── am-fin-agent/                # L3 finance
├── am-dev-agent/                # L3 dev — add HTTP Phase 3
├── am-modern-ui/am_ai_ui/       # L1 — gateway client Phase 1
├── ai-video-editor/video_pipeline/  # L4 source — wrap not fork
└── am-agents/docs/
    └── ENTERPRISE_AGENT_ECOSYSTEM.md
```

**K8s namespaces (preprod):**

| Service | Namespace | Port |
|---------|-----------|------|
| am-mcp-gateway | am-apps-preprod | 8120 |
| am-fin-agent | am-apps-preprod | 8100 |
| am-tool-agent | am-apps-preprod | 8141 |
| am-ui-test-agent | am-apps-preprod | 8130 |
| am-scribe-agent | am-apps-preprod | 8150 |
| am-devops-agent | am-apps-preprod | 8151 |
| am-video-agent | am-apps-preprod | 8156 |
| company-memory | am-apps-preprod | 8157 |
| kagent UI | kagent | 8080 |

---

## 10. Execution playbook (per phase)

### Phase 1 execution order (when user says "execute")

1. Create `am-mcp-gateway/config/agents.yaml` with fin, test, devops entries
2. Add `app/routing/registry.py` + `app/routing/router.py`
3. Add `app/sse/events.py` normalized emitter
4. Refactor `app/api/chat.py` to use router (keep finance path as first registered agent)
5. Create `am-agents/devops-agent/` minimal FastAPI — proxy tool-agent + document k8s MCP sidecar
6. Update `am-modern-ui/am_ai_ui/lib/data/ai_chat_service.dart` → gateway URL + SSE parser
7. Postman collection for 3 agent smoke tests
8. Helm values for devops-agent deployment

### Definition of done (whole program)

- [ ] One UI, one gateway, zero direct UI→agent paths (except IDE MCP)
- [ ] Scribe captures meetings → company memory
- [ ] REQ lifecycle visible on board: draft → released → supported
- [ ] All agents on LiteLLM + Langfuse
- [ ] No db-agent changes; no duplicate infra clients
- [ ] video-agent and tool-agent are only capability entry points for their domains

---

## 11. Component checklist (copy into PRs)

- [ ] Layer L1–L4 identified
- [ ] No duplicate of existing agent/capability
- [ ] Routes through gateway (if user-facing)
- [ ] Uses `agents.yaml` registry (if L3)
- [ ] Uses company memory (if requirement-related)
- [ ] Uses LiteLLM (if LLM call)
- [ ] SSE events match standard schema
- [ ] Langfuse: `agentId`, `requirementId`, `traceId`
- [ ] RBAC role documented
- [ ] Tests: unit + smoke corpus entry

---

## 12. References

| Doc | Path |
|-----|------|
| Tool-agent MCP contract | `am-agents/tool-agent/docs/MCP_CONTRACT.md` |
| Gateway chat router | `am-platform/am-mcp-gateway/app/api/chat.py` |
| fin-agent architecture | `am-fin-agent/docs/ARCHITECTURE.md` |
| Flutter AI widgets | `am-modern-ui/docs/AI_WIDGET_ARCHITECTURE.md` |
| kagent preprod | `am-agents/k8s/kagent/README.md` |
| Video pipeline 7-layer model | `ai-video-editor/video_pipeline/docs/architecture.md` |
| am-infra-ops agent template | `am-agents/k8s/kagent/agent-am-infra-ops.yaml` |

---

## 14. Meeting agent integration (Zoho, Google Meet, Teams)

How the **Scribe / meeting agent** joins live calls, understands **company profile data**, answers questions in-meeting (optional), and after the call produces **notes, MOM, and tasks**.

### 14.1 What the meeting agent does

| Mode | During meeting | After meeting |
|------|----------------|---------------|
| **Listen-only (default)** | Joins as bot, transcribes, no speech | MOM, notes, tasks, requirements → company memory |
| **Active participant (opt-in)** | Transcribes + can answer from company RAG when addressed | Same + log of Q&A pairs |
| **Manual fallback** | User uploads recording or pastes transcript | Same pipeline without bot |

**Outputs (always):**

- Structured **transcript** (speaker diarization if available)
- **Meeting summary** + **MOM** (Minutes of Meeting) — PDF/Markdown/email
- **Action items** → tasks in Zoho Projects / Jira / Linear
- **Requirements & decisions** → company memory (REQ objects)
- Optional: Slack/Teams channel post with MOM link

### 14.2 End-to-end flow

> **Diagram (Draw.io):** [enterprise-agent-ecosystem.drawio](diagrams/enterprise-agent-ecosystem.drawio) (pages **Chat Flow**, **Integration Flow**)


### 14.3 Architecture components (no duplicates)

| Component | Layer | Role | Existing reuse |
|-----------|-------|------|----------------|
| **Calendar sync** | Integration | Read meetings, auto-join | New |
| **Meeting bot adapter** | Integration | Join call, capture audio | New (or Recall.ai) |
| **STT service** | L4 / video-agent | Real-time + batch transcription | `video-agent` / `tagging.py` Whisper |
| **scribe-agent** | L3 | Extract MOM, tasks, requirements | Phase 2 |
| **Company profile RAG** | L4 module in memory | Products, org, policies, past decisions | company-memory + Qdrant |
| **company-memory** | L4 | Store meetings, REQs, decisions | Phase 2 |
| **Task MCP** | L4 satellite | Zoho Projects / Jira / Linear | Phase 3 |
| **Notify MCP** | L4 satellite | Email, Slack, Teams post-MOM | Phase 3 |
| **Enterprise UI** | L1 | Meeting list, MOM viewer, approve tasks | am-modern-ui |

**Rule:** Bot adapter only captures audio and metadata — all intelligence lives in **scribe-agent**, not in the bot SDK.

### 14.4 Company profile data (how agent “knows” the company)

The agent does **not** hallucinate company facts. It retrieves from a **Company Profile Knowledge Base** before answering.

**Sources indexed into Qdrant (+ Postgres metadata):**

| Source type | Examples | Update cadence |
|-------------|----------|----------------|
| **Static profile** | Mission, products, org chart, glossary | Admin upload / quarterly |
| **Company memory** | Past meetings, decisions, requirements | After every meeting |
| **Internal docs** | Confluence, Notion, Google Drive (read-only) | Daily sync |
| **Product data** | Public portfolio features (not end-user PII) | Weekly |
| **Policies** | HR, security, compliance | On change |

**RAG flow when participant asks in meeting:**

```
Question detected ("Hey AM bot, what's our ETF launch date?")
  → embed question
  → Qdrant search: company_profile + requirements + past_meetings
  → top-k chunks + REQ-002 metadata
  → LiteLLM answer with citations only from retrieved chunks
  → if confidence low: "I don't have that on record — I'll note it for follow-up"
```

**Security:** Meeting bot uses **service account** scoped to org docs; no end-user portfolio PII in meeting RAG unless explicitly allowed by RBAC.

### 14.5 Platform integration options

#### Option A — Unified bot provider (recommended for multi-platform)

Use one vendor that joins **Google Meet, Teams, and Zoom** via single API:

| Provider | Pros | Cons |
|----------|------|------|
| **[Recall.ai](https://recall.ai)** | One API, Meet+Teams+Zoom, webhooks, recording | Paid SaaS |
| **Meeting BaaS (e.g. Symbl, AssemblyAI streaming)** | Strong STT | May need separate join layer for Zoho |

**Flow:** Calendar event → your scheduler → `POST /bot` to Recall → webhook `transcript.partial` / `transcript.done` → scribe-agent.

#### Option B — Per-platform native

| Platform | Join method | Calendar | Notes |
|----------|-------------|----------|-------|
| **Google Meet** | Google Meet API + workspace add-on OR Recall bot | Google Calendar API | Workspace admin install |
| **Microsoft Teams** | Teams Bot Framework + Graph API OR Recall | Outlook/Graph calendar | Azure Bot registration |
| **Zoho Meeting** | Zoho Meeting API (recording webhook) OR manual upload | Zoho Calendar | Weakest bot API — often **recording post-meeting** first |

**Zoho reality:** Zoho Meeting has limited live-bot support compared to Meet/Teams. Practical rollout:

1. **Phase 2:** Zoho recording webhook or manual upload → same scribe pipeline  
2. **Phase 3:** Live bot for **Google Meet + Teams** first  
3. **Phase 4:** Zoho live join if API available, else stay on upload/webhook

### 14.6 Calendar & auto-join

> **Diagram (Draw.io):** [enterprise-agent-ecosystem.drawio](diagrams/enterprise-agent-ecosystem.drawio) (page **Portal B Screens** — Meetings tab)


**Join rules (config in Vault):**

- Join if event title contains `[AM-Bot]` OR attendee list includes `scribe-bot@yourcompany.com`
- Join only internal meetings (domain allowlist)
- Never join external/customer calls without `customer_calls_enabled=true`

**New service:** `am-meeting-scheduler` (small FastAPI worker) — Phase 3. Can live inside `scribe-agent` initially.

### 14.7 Post-meeting: MOM and tasks

**scribe-agent post-processing pipeline (LangGraph):**

```
1. ingest transcript (+ speaker labels)
2. LLM extract:
   - attendees, date, title
   - agenda items discussed
   - decisions (numbered)
   - action items (owner, due date, priority)
   - open questions / parking lot
   - requirements (REQ-xxx) if product-related
3. write company-memory
4. generate MOM document (Markdown → PDF optional)
5. task MCP: create one ticket per action item
6. notify MCP: email MOM to attendees + Slack #team channel
7. gateway/UI: meeting appears on requirements board
```

**MOM template sections:**

1. Meeting metadata (date, attendees, duration)  
2. Executive summary (3–5 bullets)  
3. Discussion notes by topic  
4. Decisions made  
5. Action items table (owner | task | due | ticket link)  
6. Next meeting / follow-ups  

**Task creation mapping:**

| Action item text | Route to | MCP |
|------------------|----------|-----|
| Engineering work | dev-agent queue | Jira/Linear `create_issue` |
| Marketing deliverable | marketing-agent tag | Zoho Projects / Jira |
| Support FAQ needed | support-agent | Zoho Desk / Zendesk |
| Admin/compliance | admin-agent | Internal tracker |

Company memory stores `action_item.ticket_url` — single traceability chain.

### 14.8 Tech stack requirements

| Requirement | Technology | Notes |
|-------------|------------|-------|
| Meeting join | Recall.ai API **or** Teams Bot + Meet add-on | Start with one platform |
| Real-time STT | Whisper (Together/LiteLLM) or Deepgram/AssemblyAI streaming | Reuse video-agent |
| Diarization | Provider-native or pyannote | Speaker-attributed MOM |
| LLM extraction | LiteLLM → DeepSeek/Gemini | Same as all agents |
| Company RAG | Qdrant + Postgres metadata | company-memory Phase 2 |
| Task sync | Zoho Projects API, Jira REST, Linear API | One MCP per vendor |
| Email MOM | SMTP / SendGrid / Zoho Mail API | Template HTML |
| Slack/Teams notify | Slack MCP, Graph send channel message | Phase 3 |
| Secrets | Vault paths for all OAuth tokens | No tokens in git |
| Auth | Keycloak for UI; service accounts for bots | RBAC on profile docs |
| Storage | Postgres meetings table; S3 for recordings optional | Retention policy |
| Tracing | Langfuse spans: bot → scribe → task | Full audit |

**Infrastructure (preprod cluster):**

```
am-scribe-agent          :8150
am-meeting-scheduler     :8158  (optional sidecar/worker)
am-company-memory        :8157
Recall.ai webhook ingress → Traefik → scribe-agent /webhooks/recall
```

### 14.9 OAuth & credentials needed

| Integration | OAuth / credential | Vault path (example) |
|-------------|-------------------|----------------------|
| Google Meet + Calendar | Google Workspace service account | `secret/am/meet-bot` |
| Microsoft Teams | Azure AD app + Bot Framework | `secret/am/teams-bot` |
| Zoho Meeting | Zoho OAuth client | `secret/am/zoho-meeting` |
| Zoho Projects (tasks) | Zoho OAuth | `secret/am/zoho-projects` |
| Recall.ai | API key | `secret/am/recall-ai` |
| SendGrid / Zoho Mail | API key | `secret/am/email` |
| Slack | Bot token | `secret/am/slack` |

### 14.10 Phased rollout (fits master plan)

| Phase | Meeting capability | Platforms |
|-------|-------------------|-----------|
| **2** | Manual transcript upload → MOM + tasks + memory | All (paste/upload) |
| **2** | Company profile RAG (static docs + memory) | Q&A in enterprise UI |
| **3** | Calendar sync + auto-join live bot | Google Meet **or** Teams (pick one) |
| **3** | Active Q&A mode in meeting (opt-in) | Same platform |
| **3** | Jira/Linear/Zoho task MCP | Task creation |
| **4** | Email/Slack MOM delivery | All attendees |
| **4** | Zoho Meeting webhook/recording | Zoho |
| **5** | Multi-platform via Recall.ai | Meet + Teams + Zoom |
| **5** | Customer call mode with stricter RBAC | Sales/support |

### 14.11 Example user experience

**Before meeting:** Organizer adds `scribe-bot@company.com` to Google Calendar invite (or tags title `[AM-Bot]`).

**During meeting (active mode):**  
Participant: *"What's the status of REQ-005 ETF API?"*  
Bot (voice or chat): *"REQ-005 is in progress — dev PR #142 merged yesterday, test run pending. Source: 12 June standup."*

**Within 5 minutes after meeting:**  
- Attendees receive **MOM email** with decisions and action table  
- **Zoho/Jira tasks** created and linked  
- **Enterprise UI** shows meeting card with link to requirements board  
- **dev-agent** can pick up tasks: *"Implement action item from MOM 17-June"*

### 14.12 Anti-duplication for meeting features

| Do | Don't |
|----|-------|
| One scribe-agent for all platforms | Separate MOM bot per vendor |
| Bot adapter = audio + webhooks only | LLM logic inside Recall callbacks |
| Company facts from RAG only | Hardcode company profile in prompt |
| Tasks in company memory first, sync out | Jira as only store |
| Reuse video-agent STT | New Whisper deployment per service |

---

## 13. Next action

**Start Phase 0 + Phase 1** when VPS is reachable:

1. Deploy tool-agent + kagent manifests
2. Implement gateway registry + router + SSE schema
3. Create devops-agent wrapper (copy am-infra-ops prompt, call existing MCPs)
4. Point Flutter ai-chat at gateway

Say **"execute Phase 1"** to begin implementation.
