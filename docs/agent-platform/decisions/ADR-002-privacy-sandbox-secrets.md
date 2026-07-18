# ADR-002 — Agent privacy, secret isolation, and tool sandbox

**Status:** Proposed (blocks design confirmation)  
**Date:** 2026-07-18  
**Repo:** am-agents  
**Parent:** [DESIGN.md](../DESIGN.md) · [ADR-001](ADR-001-temporal-agent-ports.md)

## Context

Big-tech agent platforms (tool brokers, secret managers, sandboxed tool runners) never let the LLM or agent prompt plane see raw credentials, full `os.environ`, or unrestricted network. Our design named ports and redaction lightly but did **not** lock a credential/sandbox boundary. That is a P0 gap before coding.

## Decision

### 1. Two planes (mandatory)

| Plane | Runs | May hold secrets? | Sees |
|-------|------|-------------------|------|
| **Control plane** | Temporal worker activities, adapters, SecretBroker | Yes (in-memory / Vault client only) | Full refs + secret material briefly to call APIs |
| **Reasoning plane** | LLM calls, triage reasoning, agent “thought” prompts | **Never** | Redacted DTOs, prompt keys, tool *schemas*, tool *results already sanitized* |

### 2. No env / creds to LLM or agent prompts

**Forbidden** in any message sent to an LLM, PromptRegistry render vars destined for LLM, Langfuse traces of prompts, Cliq/ticket bodies from agent summarizers:

- Raw env dumps, `os.environ`, `.env` files  
- API keys, tokens, passwords, private keys, connection strings  
- Vault paths’ **values** (path names may appear as opaque refs)  
- Full kubeconfigs, cloud SA JSON  

**Allowed:** opaque refs (`secret_ref`, `ticket_ref`), non-secret labels, redacted previews (`sk-***`).

### 3. SecretBroker port (control plane only)

```text
SecretBroker.resolve(secret_ref) -> SecretHandle   # not a string in logs
SecretBroker.inject(secret_ref, adapter_call)      # adapter receives token; LLM never does
```

- Adapters (OpenProject, Cliq, MinIO, Grafana, LLM gateway auth) pull secrets **inside** the adapter via SecretBroker.
- Activities pass `secret_ref` / config names only — **never** secret values in Temporal payloads or workflow history.
- Worker env may mount Vault/K8s secrets for the broker; agent code does not `os.getenv("OPENPROJECT_TOKEN")` in LLM paths.

### 4. Tool sandbox for all side-effect / query tools

Every tool/query execution goes through **ToolSandbox**:

| Control | Rule |
|---------|------|
| Allowlist | Tool name + args schema; deny-by-default |
| Network | Egress allowlist (OP/Cliq/MinIO/Grafana/LLM gateway only); no open internet from sandbox |
| Env | **Empty env** (or scrubbed allowlist of non-secret flags) — **no** inherited worker env |
| FS | Read-only except scratch dir; no `/var/run/secrets` mount into sandbox |
| CPU/mem/time | Hard limits; kill on exceed |
| Output | Size cap + **Redactor** before result returns to reasoning plane |
| Audit | tool_id, args (redacted), caller workflow_id, allow/deny |

InfraOps / SPT / observe queries **must** use ToolSandbox. No direct `subprocess` with full env from agent code.

### 5. LLM gateway only

- Single `LlmPort.complete(messages, *, model_ref)` — auth attached by gateway adapter via SecretBroker.
- Agents do not embed provider API keys in client constructors from env in the reasoning path.
- Prompt + tool results pass through **Redactor** before `LlmPort`.

### 6. Data minimization & classification

| Class | Examples | LLM? | Cliq/ticket? |
|-------|----------|------|--------------|
| `public` | alert name, env label | yes | yes |
| `internal` | service, namespace, runbook URL | yes (trimmed) | yes |
| `sensitive` | emails, hostnames, log snippets | redacted / truncated | redacted |
| `secret` | tokens, passwords | **never** | **never** |

`work_done` and DocStore content must run through Redactor before notify/docs.

### 7. Temporal / logging

- Workflow inputs/outputs: no secret values (refs only).  
- Activity logs: structured; auto-redact patterns (`Bearer `, `api_key=`, PEM blocks).  
- Langfuse/prompt traces: same redaction; disable raw tool-arg capture for secret fields.

## Consequences

- Phase 0b adds ports: `SecretBroker`, `ToolSandbox`, `Redactor`, `LlmPort` (stubs + fakes).  
- Phase 1 OpenProject/Cliq adapters use SecretBroker; triage LLM (if on) uses LlmPort + Redactor.  
- Phase 2+ InfraOps/SPT blocked without ToolSandbox.  
- Design confirmation requires accepting ADR-002.
