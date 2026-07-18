"""Composition and adapter boundaries for support-agent.

`build_runtime()` is the single composition root. Ports live under
`am_support_agent.ports`; vendor I/O stays in tool-agent.

Env (selected):
- `SUPPORT_AGENT_RUNTIME_MODE` = `dev` | `test` | `prod`
- `SUPPORT_AGENT_REQUIRE_LIVE_ADAPTERS` = fail-closed readiness when true
- `SUPPORT_AGENT_CAPABILITY_PROVIDER` = `tool-agent` (default) | `fake`
- `SUPPORT_AGENT_DOC_PROVIDER` = `memory` (default) | `minio`
- `SUPPORT_AGENT_LLM_PROVIDER` = `gated` (default) | `fake`
- `SUPPORT_AGENT_PROMPT_SOURCE` = `file` (default) | `langfuse`
- `SUPPORT_AGENT_INCIDENT_PARITY` / `SUPPORT_AGENT_SPT_PARITY` = enable side-effect paths

Runtime also exposes in-memory episode/feedback stores plus security stubs
(`Redactor`, `SecretBroker`, `SandboxPolicy`). Qdrant and durable episode
Postgres remain post-canary.
"""
