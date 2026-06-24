# Prompt management

## Sources

| Source | Use |
|--------|-----|
| `PROMPT_SOURCE=file` | Local dev — reads `tools/*/prompts/*.yaml` |
| `PROMPT_SOURCE=langfuse` | Runtime — fetches from Langfuse with file fallback |

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
