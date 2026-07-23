# SPT store cutover (JSON ↔ DB)

## Modes (`SPT_STORE`)

| Value | Read | Write |
|-------|------|-------|
| `json` | `runs.json` / `configs.json` | JSON only (rollback) |
| `dual` | DB, fallback JSON | DB + JSON |
| `db` | DB | DB only (**default**) |

SQLite file: `{DATA_DIR}/spt.db` unless `SPT_DATABASE_URL` is set (Postgres).

## Cutover steps

1. Deploy with `SPT_STORE=dual`
2. Backfill: `python -m app.db.migrate_json`
3. Parity: `python -m app.db.migrate_json --parity 50` (exit 1 on mismatch)
4. Switch to `SPT_STORE=db`
5. Keep JSON files for one release

## Rollback

Set `SPT_STORE=json` and restart. JSON must still exist from dual-write or a prior export.

## Health

`GET /health` includes `store`, `db`, and `latency.list_10_runs_ms` (SLO &lt; 50ms local).
