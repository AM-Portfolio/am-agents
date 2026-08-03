# Finance AI chat — pre-release gate (R0a / R0b / R1 / R2)

**No preprod/prod promote** of `am-fin-agent` or `am-ai-gateway` until all gates below are green and this file records evidence.

Runtime under test: **am-ai-gateway** (`mcp-gateway/`) → **fin-portfolio-agent** (`am-fin-agent`). Do **not** use `am-asrax-proxy` / product API gateway for AI chat.

---

## Fixture user

| Variable | Value | Notes |
|----------|-------|-------|
| JWT | Keycloak / api-key access token | Identity = JWT `sub`. Body `userId` optional and ignored when Bearer present. |
| `AUTH_REQUIRED=true` | Bearer required | Missing/invalid token → 401 |

Never use literal `fin-agent` as identity. Do not rely on stale fixture UUIDs in the chat body.

---

## Env lock (before R0a)

- [ ] Pods Ready: `am-fin-agent`, `am-ai-gateway` in target ns (e.g. `am-apps-dev`)
- [ ] Agent env: `LANGFUSE_ENABLED=true`, `LANGFUSE_HOST`, keys from Vault, `LANGFUSE_ENV=dev`
- [ ] Agent prompt: `PROMPT_SOURCE=langfuse` (cluster) or `file` (local); label `PROMPT_LABEL=dev` until R1 promote
- [ ] Gateway: `FINANCE_AGENT_BASE_URL` → fin-agent service; forwards `Authorization`, `X-Request-Id`, `X-Session-Id`
- [ ] Downstream portfolio/analysis health so empty portfolio is visible, not silent 5xx

Example (public domain — preferred, no port-forward):

```bash
# Chat: https://am-dev.asrax.in/ai/api/v1/ai/chat
# Health: https://am-dev.asrax.in/ai/health
```

Emergency fallback only (if ingress down):

```bash
kubectl -n am-apps-dev port-forward svc/am-ai-gateway 8120:8120
```

---

## R0a — HTTP smoke (via gateway)

Target: `https://am-dev.asrax.in/ai/api/v1/ai/chat` with fixture JWT (`AUTH_REQUIRED=true`).

| # | message | Expect `artifactType` | Also |
|---|---------|----------------------|------|
| 1 | portfolio summary | `portfolio.summary.v1` | `toolsUsed` includes `get_portfolio_summary`; `data` present |
| 2 | show my holdings | `holdings.list.v1` | `get_holdings` |
| 3 | top movers | `portfolio.movers.v1` | `get_top_movers` |
| 4 | sector allocation | `portfolio.sector_allocation.v1` | `get_sector_allocation` |
| 5 | hello | `text.v1` | HTTP 200; no `ask_finance_agent` |

Auth: no Bearer → 401; with Bearer → 200.

```bash
curl -sS -X POST "$GW/api/v1/ai/chat" \
  -H "Content-Type: application/json" \
  -H "X-Request-Id: $(uuidgen)" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"message":"portfolio summary","sessionId":"r0a-smoke"}'
```

Golden file: `eval/fin_chat_golden.json` (v2, artifactType). Runner: `scripts/eval_fin_chat.py`.

**R0a result:** _pending_  
Date / operator / notes: _

---

## R0b — Langfuse correlation (after P0 deploy)

- [ ] Multi-turn same `sessionId` → one Langfuse session, N turn traces
- [ ] Each response `traceId` matches Langfuse turn / `X-Trace-Id`
- [ ] Langfuse `userId` = JWT `sub` (not `fin-agent`); tags include `fin-agent`, `env:dev`, `surface:chat`
- [ ] Spans: at least one generation; data turns include tool span
- [ ] Sent `X-Request-Id` appears in trace metadata as `requestId`

**R0b result:** _pending_  
Langfuse project / sample session URL: _

---

## R1 — Golden experiment

1. Seed Langfuse prompt `fin-agent/system` from `prompts/fin_agent_system.md` (label `dev`):

```bash
export LANGFUSE_PUBLIC_KEY=... LANGFUSE_SECRET_KEY=... LANGFUSE_HOST=...
python scripts/seed_fin_agent_prompt.py --label dev
```

2. Upload/mirror dataset `fin-chat-golden` from `eval/fin_chat_golden.json`.
3. Run:

```bash
cd am-agents/fin-portfolio-agent
export EVAL_GATEWAY_URL=https://am-dev.asrax.in/ai
export EVAL_USER_ID=<fixture>
# export EVAL_BEARER_TOKEN=...   # if AUTH_REQUIRED
python scripts/eval_fin_chat.py
```

4. **100% pass** (one retry per item allowed).  
5. Record: agent image, gateway image, git SHA, prompt name/version/label.  
6. Spot-check 2 traces in Langfuse UI.

**R1 result:** _pending_  
Experiment / run notes: _  
Git SHA: _  
Agent image: _  
Gateway image: _  
Prompt version/label: _

---

## R2 — UI smoke

- [ ] `am-modern-ui` with domain `am-dev.asrax.in` (uses `$apiBase/ai` → public gateway)
- [ ] Admin login → `/app/ai-chat`
- [ ] Portfolio summary → `PORTFOLIO_SUMMARY` card
- [ ] View details → real app route
- [ ] No blocking console/network errors

**R2 result:** _pending_  
Notes: _

---

## Sign-off

- [ ] Env lock verified  
- [ ] R0a green  
- [ ] R0b green  
- [ ] R1 green (100% + SHA recorded)  
- [ ] R2 green  
- [ ] Rollback tags recorded below  
- [ ] `am-api-gateway` not required for this release  

Signed: _  
Date: _

---

## Rollback

| Component | Previous tag / revision | How |
|-----------|-------------------------|-----|
| `am-fin-agent` | _ | Helm/image rollback to prior tag |
| `am-ai-gateway` | _ | Helm/image rollback to prior tag |
| Langfuse prompt `fin-agent/system` | _ | Re-point label `production`/`preprod` to previous version |

Fail-open note: Langfuse outage must not break chat; if prompt `PROMPT_SOURCE=langfuse` fails, agent falls back to cache then `prompts/fin_agent_system.md`. To force file prompts: set `PROMPT_SOURCE=file` and restart.

---

## Deferred (post first green release)

- MCP commercial packaging  
- Calibrated LLM-as-judge as blocking gate  
- Prod SLO alerting  
- Replacing `am-asrax-proxy`
