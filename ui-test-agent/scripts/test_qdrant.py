#!/usr/bin/env python3
"""
Verify Qdrant connectivity for am-ui-test-agent (design review baselines).

Usage:
  python scripts/test_qdrant.py
  python scripts/test_qdrant.py --env-file .env.preprod
  python scripts/test_qdrant.py --host localhost --port 6333
  python scripts/test_qdrant.py --skip-write
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_COLLECTIONS = ("ui_patterns", "test_cases", "selectors", "bug_memory")


def _ok(label: str, detail: str = "") -> dict[str, Any]:
    return {"step": label, "status": "ok", "detail": detail}


def _fail(label: str, detail: str) -> dict[str, Any]:
    return {"step": label, "status": "fail", "detail": detail}


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Qdrant connectivity for ui-test-agent")
    parser.add_argument(
        "--env-file",
        default=os.environ.get("ENV_FILE_PATH", ".env.preprod"),
        help="Env file for QDRANT_HOST / QDRANT_PORT / QDRANT_API_KEY",
    )
    parser.add_argument("--host", default=None, help="Override QDRANT_HOST")
    parser.add_argument("--port", type=int, default=None, help="Override QDRANT_PORT")
    parser.add_argument("--https", action="store_true", help="Use HTTPS (override QDRANT_HTTPS)")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Force plain HTTP (override QDRANT_HTTPS)",
    )
    parser.add_argument(
        "--skip-write",
        action="store_true",
        help="Only check connection and collections (no upsert/search/delete)",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON result")
    args = parser.parse_args()

    env_path = Path(args.env_file)
    if not env_path.is_absolute():
        env_path = (ROOT / env_path).resolve()
    os.environ["ENV_FILE_PATH"] = str(env_path)
    if args.host:
        os.environ["QDRANT_HOST"] = args.host
    if args.port is not None:
        os.environ["QDRANT_PORT"] = str(args.port)
    if args.https:
        os.environ["QDRANT_HTTPS"] = "true"
    if args.http:
        os.environ["QDRANT_HTTPS"] = "false"
    sys.path.insert(0, str(ROOT))

    from qdrant_client.http.models import PointStruct

    from app.config import settings
    from app.memory.embedder import UI_PATTERN_DIM
    from app.memory.qdrant import QdrantMemory

    host = settings.QDRANT_HOST
    port = settings.QDRANT_PORT
    api_key = settings.QDRANT_API_KEY
    https = settings.QDRANT_HTTPS
    scheme = "https" if https else "http"

    results: list[dict[str, Any]] = []
    summary = {
        "endpoint": f"{scheme}://{host}:{port}",
        "host": host,
        "port": port,
        "https": https,
        "env_file": str(env_path),
        "api_key_set": bool(api_key),
    }

    print(f"Qdrant health check -> {scheme}://{host}:{port} (env: {env_path.name})")

    memory = QdrantMemory()
    if not memory.available or not memory.client:
        results.append(_fail("connect", "QdrantMemory client unavailable"))
        _emit(args.json, summary, results, ok=False)
        return 1

    client = memory.client
    try:
        collections = [c.name for c in client.get_collections().collections]
        results.append(_ok("connect", f"{len(collections)} collection(s) visible"))
    except Exception as exc:
        results.append(_fail("connect", str(exc)))
        _emit(args.json, summary, results, ok=False)
        return 1

    missing = [name for name in EXPECTED_COLLECTIONS if name not in collections]
    if missing:
        results.append(_fail("collections", f"missing: {', '.join(missing)}"))
    else:
        results.append(_ok("collections", ", ".join(EXPECTED_COLLECTIONS)))

    if args.skip_write:
        ok = all(r["status"] == "ok" for r in results)
        _emit(args.json, summary, results, ok=ok)
        return 0 if ok else 1

    test_id = f"qdrant-health-{uuid.uuid4().hex[:8]}"
    vector = [0.01] * UI_PATTERN_DIM
    point_id = str(uuid.uuid4())

    try:
        client.upsert(
            collection_name="bug_memory",
            points=[
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={"source": "test_qdrant.py", "test_id": test_id},
                )
            ],
        )
        results.append(_ok("upsert", f"bug_memory point {point_id[:8]}..."))
    except Exception as exc:
        results.append(_fail("upsert", str(exc)))
        _emit(args.json, summary, results, ok=False)
        return 1

    try:
        hits = client.search(collection_name="bug_memory", query_vector=vector, limit=3)
        found = any(str(hit.id) == point_id for hit in hits)
        if not found:
            results.append(_fail("search", "upserted point not returned by vector search"))
        else:
            top_score = next(h.score for h in hits if str(h.id) == point_id)
            results.append(_ok("search", f"found test point (score={top_score:.4f})"))
    except Exception as exc:
        results.append(_fail("search", str(exc)))

    try:
        client.delete(collection_name="bug_memory", points_selector=[point_id])
        results.append(_ok("cleanup", "deleted test point"))
    except Exception as exc:
        results.append(_fail("cleanup", str(exc)))

    ok = all(r["status"] == "ok" for r in results)
    _emit(args.json, summary, results, ok=ok)
    return 0 if ok else 1


def _emit(json_mode: bool, summary: dict[str, Any], results: list[dict[str, Any]], *, ok: bool) -> None:
    if json_mode:
        print(json.dumps({"ok": ok, **summary, "steps": results}, indent=2))
        return

    for step in results:
        mark = "PASS" if step["status"] == "ok" else "FAIL"
        detail = f" - {step['detail']}" if step.get("detail") else ""
        print(f"  [{mark}] {step['step']}{detail}")
    print("Result:", "OK" if ok else "FAILED")


if __name__ == "__main__":
    raise SystemExit(main())
