# JWT and API Keys Handoff — fin-portfolio-agent

## Status — 2026-08-02

- Core JWT propagation, authenticated MCP transport, Helm wiring, and launcher/docs exist in the local working tree.
- Repository: `am-agents` on `feature/ai-chat-l3`, with substantial uncommitted work.
- Deployment freshness is not proven; the cluster may still run an older image.
- `AUTH_REQUIRED` remains `false` pending a domain smoke test.

## Goal / architecture

“Call Asrax” AI is `fin-agent`, exposed in dev through:

`https://am-dev.asrax.in/ai` → AI gateway → fin-agent → `am-analysis`

Authentication rules:

- JWT `sub` is the user identity and authoritative `userId`.
- API keys are credentials only for identity token exchange.
- Exchange a key at identity, then send the returned short-lived JWT as `Authorization: Bearer <token>`.
- Never send a raw API key to fin-agent as the Authorization credential.
- Fin-agent forwards the same Bearer token to `am-analysis`.

## Git topology

- `AM-Portfolio-grp` is **not** a Git repository; its parent `.git` was removed.
- Work and commit only in nested repositories:
  - `am-agents`
  - `am-platform`
  - `am-modern-ui`
  - `am-gateways`
- Do not run branch/commit operations from the workspace root.

## Implemented and verified in the tree

### Request identity and analysis calls

- `shared/context/request_context.py` defines `auth_token_var` as a `ContextVar`.
- Auth middleware captures the incoming Bearer token and token subject.
- JWT `sub` is used as request identity when a valid token is present.
- `AnalysisClient` reads `auth_token_var` and forwards `Authorization: Bearer ...`.
- Analysis paths use `/v1/analysis/...`.
- Missing/rejected auth and unavailable analysis return structured error payloads.
- `ANALYSIS_BASE_URL` is configurable and wired through Helm.

### Auth enforcement

- `AUTH_REQUIRED=false` preserves the staged rollout behavior.
- When enabled, missing/invalid Bearer credentials are rejected for AI chat.
- A supplied request `userId` must match JWT `sub`.
- `AUTH_JWKS_URL` and `AUTH_ISSUER` are supported by middleware and Helm.

### MCP

- Fin-agent mounts authenticated MCP SSE at `/ai/mcp`.
- MCP validates a Bearer JWT through JWKS.
- `scripts/asrax_mcp.py` exchanges an Asrax API key for tokens, then launches
  `mcp-remote` with the short-lived Bearer token.
- `docs/MCP.md` documents the launcher and security model.
- Gateway code in `am-gateways/mcp-gateway/app/main.py` exposes `/mcp` and
  proxies Authorization/SSE traffic upstream to fin-agent `/ai/mcp`.
- Dev ingress routes public `/ai/*` through the gateway, so the intended public
  endpoint is `https://am-dev.asrax.in/ai/mcp`.
- Gateway MCP work is local/uncommitted on `am-gateways/main`; deployment status
  must be verified before treating the public route as live.

### Vault and runtime configuration

- Identity Vault path: `apps/data/dev/services/am-identity`.
- That path contains `DATABASE_URL` and `OIDC_*` values.
- Fin-agent mounts the identity path and maps:
  - `OIDC_ISSUER` → `AUTH_ISSUER`
  - `OIDC_JWKS_URL` → `AUTH_JWKS_URL`
- Helm values still set `AUTH_REQUIRED: "false"`.
- Do not copy Vault values into docs, source, logs, or chat.

## Shared environment facts

- PostgreSQL database: `am_identity`.
- Migration `001_create_api_keys.sql` has been applied on the VPS.
- Postman workspace: Asrax, ID `648a186b-f56c-4a95-b8ff-9a235cbde152`.
- Collection: **AM Identity Service**.
- Folder: **06 API Keys**.
- Useful environments:
  - **AM Fin-Agent - Dev**
  - **AM Platform - Dev**

## Left / blockers — ordered

1. Redeploy/verify the latest fin-agent image; local WIP may not be on the cluster.
2. Obtain a JWT through identity API-key exchange and run a real domain smoke:
   ask Call Asrax for a portfolio summary and confirm `am-analysis` returns the
   authenticated user's data.
3. Confirm the propagated identity is JWT `sub`, with no body `userId` override.
4. Confirm public MCP `/ai/mcp` after deploying the gateway changes.
5. Flip `AUTH_REQUIRED=true` only after the authenticated chat and MCP smoke pass.
6. Re-run evals with `EVAL_BEARER_TOKEN` when auth is required.
7. Commit and open review from the existing feature branch; do not include secrets.

## How to continue

1. Start in the nested repo and inspect WIP:
   `cd a:\InfraCode\AM-Portfolio-grp\am-agents && git status --short --branch`
2. Verify the deployed image/config and that `AUTH_JWKS_URL`,
   `AUTH_ISSUER`, and `ANALYSIS_BASE_URL` are populated without printing secrets.
3. Use Postman folder **06 API Keys** to exchange a key for a JWT, then smoke
   `https://am-dev.asrax.in/ai` and `/ai/mcp` with Bearer auth.

After the smoke:

- Set `AUTH_REQUIRED=true` in the dev deployment.
- Repeat missing-token, invalid-token, mismatched-user, and valid-token cases.
- Run `scripts/eval_fin_chat.py` with `EVAL_BEARER_TOKEN` set securely.

## Success criteria

- A valid exchanged JWT yields a real portfolio summary for its `sub`.
- Fin-agent and `am-analysis` receive Bearer auth; neither receives a raw API key.
- Missing or invalid JWTs fail predictably once `AUTH_REQUIRED=true`.
- MCP SSE works through the public gateway route.
- No secrets or JWTs are committed or pasted into logs/docs.

## Cross-repository handoffs

- Identity: `am-platform/am-identity/docs/HANDOFF_API_KEYS.md`
- UI: `am-modern-ui/docs/HANDOFF_API_KEYS.md`
- Gateway implementation: `am-gateways/mcp-gateway/`
