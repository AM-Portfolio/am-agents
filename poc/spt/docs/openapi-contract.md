# SPT ↔ service OpenAPI contract

SPT builds Try-it / load payloads from the **live OpenAPI document** only.
There is **zero coupling** to service source code (no Java imports, no hard-coded analysis enums).

## Allowed

| SPT may | How |
|---------|-----|
| Fetch `{target}{openapi.path}` | Via `spt.yaml` registration |
| Read `enum`, `example`, `default`, `format` | Generic builder |
| Store overlays + payload sets | `{data_dir}/openapi_overlays`, `{data_dir}/payloads` |
| Call Try proxy | `/api/catalog/{service}/try/...` |
| Optional LLM HTTP | `SPT_PAYLOAD_LLM_FALLBACK` + `SPT_FIN_API_TESTING_URL` (off by default) |

## Forbidden

- Importing `am-core-services` / service SDKs into SPT
- `if service == "am-analysis"` schema special cases in the builder
- Hard-coded timeframe / entity-type lists in JS or Python

## Service obligations

Publish complete springdoc OpenAPI. See:

- [am-core-services openapi-spec-guidelines.md](../../../../am-core-services/docs/openapi-spec-guidelines.md)
- [spt-onboarding.md](../../../../am-core-services/docs/spt-onboarding.md)

When a service adds an enum constant, SPT picks it up on the next OpenAPI fetch — no SPT change.

## APIs

| Endpoint | Purpose |
|----------|---------|
| `POST /api/payloads/build` | Schema-first build (overlay → example → schema) |
| `POST /api/payloads/ensure-working` | Build → Try → write set+overlay on 2xx |
| `GET /api/catalog/{service}/openapi/effective` | Live doc + SPT overlay |
| MCP `spt_build_payload` / `spt_ensure_working_payload` | Same for agents |

`source` values: `set` | `example` | `schema` | `llm-fallback`.
