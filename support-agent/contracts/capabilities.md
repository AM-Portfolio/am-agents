# Capabilities and agent cards

## Routing preference

| Capability domain | Preferred agent | Fallback |
|-------------------|-----------------|----------|
| Postgres / Mongo / Kafka / Redis / Vault / Grafana / Qdrant tools | `tool-agent` | `db-agent` only with `legacy.db-agent` |
| Browser / Playwright / visual baseline | `ui-test-agent` | none |
| MCP declarative infra agents | kagent → Tool Agent MCP bridge | Platform HTTP adapters to Tool Agent |

## Agent card fields (required)

- `agent_id`, `display_name`, `base_url`
- `capabilities[]` with `id`, `ops[]`, `preferred`
- `health.path`
- `auth` scheme
- `limits.multi_replica_status` (false for ui-test-agent)

## Auth rules

| Agent | Auth notes |
|-------|------------|
| tool-agent | As deployed (service network / token per env) |
| db-agent | Optional `X-Agent-Caller` validation |
| ui-test-agent | As deployed |
| platform gateway (legacy) | `Authorization: Bearer <GATEWAY_API_TOKEN>` |
| platform gateway (replacement) | Service tokens + allowlists; RBAC on workflow start/signal |

## Idempotency

- Platform `execute` always carries `idempotency_key`.
- Adapter maps key → specialist request headers/body fields when available; otherwise stores mapping in RunStore.
