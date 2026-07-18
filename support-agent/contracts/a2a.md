# A2A contract notes

See full normative table: [docs/architecture/a2a-protocol.md](../../docs/architecture/a2a-protocol.md).

## Specialist endpoint map

### tool-agent `:8141`

| A2A op | HTTP |
|--------|------|
| discover | `GET /health`, `GET /ready` + tool manifests |
| plan | `POST /api/v1/tools/plan` (+ `/plan/stream`) |
| execute | `POST /api/v1/tools/execute` (+ `/execute/stream`) |
| stream | SSE stream routes |
| status / cancel / feedback | **adapter-synthesized** |

Also: `POST /api/v1/tools/query` (+ stream) as a convenience capability.

### db-agent `:8140` (legacy)

| A2A op | HTTP |
|--------|------|
| discover | `GET /health`, `GET /ready` + `config/registry.yaml` |
| plan | `POST /api/v1/db/plan` |
| execute | `POST /api/v1/db/execute` |
| stream / status / cancel / feedback | **adapter-synthesized** |

Caller header: `X-Agent-Caller` when configured.

### ui-test-agent `:8130`

| A2A op | HTTP |
|--------|------|
| discover | `GET /health` + OpenAPI capabilities |
| plan | **synthesize** from run request |
| execute | `POST /api/v1/test/run` (+ `/run/auth`) |
| status | `GET /api/v1/test/status/{testId}` (process-local) |
| stream | **poll status → events** |
| report | `GET /api/v1/test/report/{testId}` (evidence) |
| cancel / feedback | **adapter-synthesized** |

**Limit:** status is not multi-replica safe. Platform must not assume HA status for UI runs.
