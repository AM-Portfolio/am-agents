# Vault (HashiCorp KV via vault-mcp)

Preprod mount: **`apps`**. MCP paths: **`preprod/{category}/{service}`** (no `apps/` or `data/` prefix after normalization).

## Path catalog

Full preprod paths and entity aliases: [`schema/preprod.yaml`](schema/preprod.yaml) (sourced from `VPS/vault/backups/` + `VPS/vault/VAULT_SCHEMA.md`).

| Category | Prefix | Examples |
|----------|--------|----------|
| infra | `preprod/infra` | postgres, mongodb, redis, kafka, influxdb, shared-api |
| services | `preprod/services` | am-identity, am-analysis, am-mcp-gateway, am-portfolio, ... |
| api | `preprod/api` | github, upstox |

## Prompts

- [`prompts/intent.yaml`](prompts/intent.yaml) — operations, path tree, NL mapping hints (injected into LLM + Langfuse)
- [`prompts/examples.yaml`](prompts/examples.yaml) — 14 few-shot intent examples

## Intent resolution

1. **parse_rules** + **fuzzy.py** — typos (`postgress`), categories (`service`/`infra`), `am-*` service names
2. **resolve.py** — entity → path via schema catalog, path normalization via [`paths.py`](paths.py)
3. **LLM fallback** — schema catalog snippet includes vault path tree when `backend=vault`

Use `params.entity` (e.g. `postgres_infra`, `am_analysis`) when possible instead of raw paths.
