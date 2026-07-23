# SPT service registration

Services register with a minimal `spt.yaml` (no auth, no API list).
SPT loads OpenAPI from the live target and injects platform identity auth.

See also:

- [am-core-services docs/spt-onboarding.md](../../../../am-core-services/docs/spt-onboarding.md)
- [am-core-services OpenAPI guidelines](../../../../am-core-services/docs/openapi-spec-guidelines.md) (enums, examples, timestamps)
- [openapi-contract.md](openapi-contract.md) (SPT zero-coupling rules)

## Contract

| Field | Required | Purpose |
|-------|----------|---------|
| `service` | yes | Stable id (Influx/Grafana tag) |
| `runtime` | yes | `java` or `python` → default OpenAPI path |
| `targets.<env>` | yes (`dev` min) | Auto-selected base URL for portal env |
| `openapi.path` | optional | Override `/v3/api-docs` (java) or `/openapi.json` (python) |
| `owners` | recommended | Team that owns the registration |
| `createdBy` / `updatedBy` | recommended | Who registered / last edited |
| `createdAt` / `updatedAt` | recommended | ISO dates (git fills gaps in Specs UI) |
| `source.repo` / `source.path` | recommended | Repo + file path for traceability |
| `traces[]` | optional | Named refs (configmap, onboarding, openapi, …) |

## Local portal

```powershell
# in am-agents/poc/spt — points SPT_CATALOG_EXTERNAL at am-core-services/services
.\scripts\run-local.ps1
# open http://localhost:8150/ui → OpenAPI → Swagger UI
```

Specs tab embeds **Swagger UI** (`swagger-ui-dist`, vendored under `app/static/vendor/swagger-ui/`).
SPT fetches OpenAPI with platform identity, then mounts the official SDK on that document.
Try it out uses `public_*` targets when set, plus `/api/platform/try-token` for Bearer auth.

Payloads: **Build** / **Ensure working** use schema-first generation (`POST /api/payloads/build`).
LLM fallback is off by default (`SPT_PAYLOAD_LLM_FALLBACK=false`).
