# Asrax Finance MCP

The authenticated SSE endpoint is `/ai/mcp` on fin-agent. Through the AI
gateway, use `https://am.asrax.in/ai/mcp` (or the matching environment host).
It accepts a short-lived Bearer access token, not a raw API key.

Create an API key with `POST /identity/users/me/api-keys`, save the returned
secret once, and configure Cursor to launch the exchange helper:

```json
{
  "mcpServers": {
    "asrax-finance": {
      "command": "python",
      "args": ["A:/InfraCode/AM-Portfolio-grp/am-agents/fin-portfolio-agent/scripts/asrax_mcp.py"],
      "env": {
        "ASRAX_KEY_ID": "asrx_...",
        "ASRAX_KEY_SECRET": "...",
        "ASRAX_IDENTITY_URL": "https://am.asrax.in/identity",
        "ASRAX_MCP_URL": "https://am.asrax.in/ai/mcp"
      }
    }
  }
}
```

The helper exchanges `key_id` and `secret` at `/auth/api-key`, then gives the
resulting Bearer token to `mcp-remote`. Do not place a browser session JWT or a
raw API key in the MCP `Authorization` header.

Server-side configuration requires `AUTH_JWKS_URL`; `AUTH_ISSUER` and
`AUTH_AUDIENCE` should also be set for the environment. `AUTH_REQUIRED` remains
`false` by default for chat until rollout is explicitly enabled.
