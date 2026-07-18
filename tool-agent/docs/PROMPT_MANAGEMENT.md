# Prompt management

## Sources

| Source | Use |
|--------|-----|
| `PROMPT_SOURCE=file` | Local / Coder — reads `tools/*/prompts/*.yaml` on every request (no restart) |
| `PROMPT_SOURCE=langfuse` | Runtime — fetches from Langfuse with TTL cache + file fallback |

## Langfuse names

- `tool-agent/intent/base`
- `tool-agent/intent/{tool}`
- `tool-agent/intent/{tool}/examples`

Labels: `preprod`, `production`, `latest` (mapped from `APP_ENV`).

## Sync git → Langfuse

```bash
python scripts/seed_prompts_to_langfuse.py --dry-run
python scripts/seed_prompts_to_langfuse.py
```

Promote labels in Langfuse UI after review.

## Coder dev loop (Langfuse, no restart)

Edit a prompt in Langfuse, refresh the running tool-agent, and confirm the resolved text — without restarting the process.

### Required env

```bash
PROMPT_SOURCE=langfuse
LANGFUSE_ENABLED=true
LANGFUSE_HOST=https://langfuse.munish.org   # or your host
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
APP_ENV=local                               # maps label → latest
TOOL_AGENT_PROMPT_ADMIN_ENABLED=true        # default true; set false in prod
# optional: TOOL_AGENT_PROMPT_CACHE_TTL_SECONDS=15
```

### Loop

1. Edit the prompt in Langfuse UI (or re-run `seed_prompts_to_langfuse.py`) and set/promote the label (`latest` for local).
2. Bust the in-process cache:

```bash
curl -X POST http://127.0.0.1:8141/api/v1/prompts/reload
```

3. Preview what the service will use:

```bash
# single template
python scripts/test_prompt.py --name tool-agent/intent/grafana --label latest

# full built intent prompt (same path as /plan)
python scripts/test_prompt.py --query "debug 500 errors for am-parser" --backend grafana
```

4. Hit a real tool call:

```bash
curl -X POST http://127.0.0.1:8141/api/v1/tools/plan \
  -H 'Content-Type: application/json' \
  -d '{"query":"debug 500 errors for am-parser","backend":"grafana"}'
```

Without an explicit reload, edits still apply after `TOOL_AGENT_PROMPT_CACHE_TTL_SECONDS` (default 60s).

### Admin endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/prompts/preview` | Resolve one template (`name`/`label`) or a built prompt (`query`/`backend`) |
| `POST` | `/api/v1/prompts/reload` | Clear Langfuse prompt cache |
| `GET` | `/api/v1/prompts/cache` | List cached entries (name, label, version, age) |

Set `TOOL_AGENT_PROMPT_ADMIN_ENABLED=false` in production values — preview returns prompt bodies.
