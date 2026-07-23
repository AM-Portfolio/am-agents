"""Idempotent JSON → DB migrator and parity check.

Usage:
  python -m app.db.migrate_json
  python -m app.db.migrate_json --parity 20
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from app.db.engine import init_db, store_mode
from app.stores import db_backend as db
from app.stores import json_backend as jb

HOT_COMPARE = (
    "id",
    "status",
    "config_id",
    "config_name",
    "service",
    "environment",
    "started_at",
    "passed",
    "api_count",
)


def _eq(a: Any, b: Any) -> bool:
    if a == b:
        return True
    if a in (None, 0) and b in (None, 0):
        return True
    return False


def migrate_all() -> dict[str, int]:
    init_db()
    runs = jb._read_json(jb.RUNS_FILE)
    configs = jb._read_json(jb.CONFIGS_FILE)
    run_n = 0
    cfg_n = 0
    for row in runs:
        if not row.get("id"):
            continue
        db.save_run(dict(row))
        run_n += 1
    for row in configs:
        if not row.get("id"):
            continue
        db.save_config(dict(row))
        cfg_n += 1
    return {"runs": run_n, "profiles": cfg_n}


def parity_check(sample: int = 20) -> dict[str, Any]:
    init_db()
    jruns, _ = jb.list_runs(limit=sample, offset=0)
    mismatches: list[dict[str, Any]] = []
    checked = 0
    for jrow in jruns:
        rid = jrow.get("id")
        if not rid:
            continue
        drow = db.get_run(str(rid))
        checked += 1
        if drow is None:
            mismatches.append({"id": rid, "error": "missing_in_db"})
            continue
        diffs = {}
        for k in HOT_COMPARE:
            jv, dv = jrow.get(k), drow.get(k)
            if not _eq(jv, dv):
                diffs[k] = {"json": jv, "db": dv}
        if diffs:
            mismatches.append({"id": rid, "diffs": diffs})
    jcfgs = jb.list_configs()
    cfg_missing = 0
    for c in jcfgs[:sample]:
        if not db.get_config(str(c.get("id"))):
            cfg_missing += 1
    return {
        "ok": not mismatches and cfg_missing == 0,
        "checked_runs": checked,
        "mismatches": mismatches,
        "profiles_missing": cfg_missing,
        "store_mode": store_mode(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate SPT JSON store → DB")
    parser.add_argument("--parity", type=int, nargs="?", const=20, help="Run parity check on N runs")
    args = parser.parse_args(argv)
    if args.parity is not None:
        result = parity_check(args.parity)
        print(result)
        return 0 if result.get("ok") else 1
    stats = migrate_all()
    print({"migrated": stats, "store_mode": store_mode()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
