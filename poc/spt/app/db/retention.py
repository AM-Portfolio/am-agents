"""Delete finished runs older than SPT_RUN_RETENTION_DAYS (metadata only; artifacts separate)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import settings
from app.db.engine import get_session, store_mode
from app.db.models import RunRow
from app.stores import json_backend as jb


def purge_old_runs(*, days: int | None = None, dry_run: bool = False) -> dict:
    days = days if days is not None else settings.spt_run_retention_days
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    deleted = 0
    if store_mode() == "json":
        rows = jb._read_json(jb.RUNS_FILE)
        kept = []
        for r in rows:
            started = str(r.get("started_at") or "")
            if r.get("status") == "running" or started >= cutoff:
                kept.append(r)
            else:
                deleted += 1
        if not dry_run:
            jb._write_json(jb.RUNS_FILE, kept)
        return {"deleted": deleted, "cutoff": cutoff, "dry_run": dry_run}
    with get_session() as session:
        rows = list(
            session.scalars(
                select(RunRow).where(RunRow.started_at < cutoff, RunRow.status != "running")
            )
        )
        deleted = len(rows)
        if not dry_run:
            for r in rows:
                session.delete(r)
    return {"deleted": deleted, "cutoff": cutoff, "dry_run": dry_run}


if __name__ == "__main__":
    print(purge_old_runs())
