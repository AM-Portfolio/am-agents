#!/usr/bin/env python3
"""
Seed Langfuse dataset fin-chat-golden from eval/fin_chat_golden.json.

Uses the public REST API (avoids SDK response-schema mismatches).

  export LANGFUSE_PUBLIC_KEY=...
  export LANGFUSE_SECRET_KEY=...
  export LANGFUSE_HOST=https://langfuse.munish.org
  python scripts/seed_fin_chat_dataset.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "eval" / "fin_chat_golden.json"


def main() -> int:
    pk = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    sk = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    host = os.getenv("LANGFUSE_HOST", "https://langfuse.munish.org").rstrip("/")
    if not pk or not sk:
        print("LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY required", file=sys.stderr)
        return 2
    if not GOLDEN.exists():
        print(f"Missing {GOLDEN}", file=sys.stderr)
        return 2

    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    name = data["dataset"]
    auth = (pk, sk)

    with httpx.Client(base_url=host, auth=auth, timeout=60.0) as client:
        # Create dataset (ignore conflict)
        r = client.post(
            "/api/public/datasets",
            json={
                "name": name,
                "description": data.get("description", ""),
                "metadata": {"version": data.get("version", 1)},
            },
        )
        print(f"dataset create: {r.status_code}")

        for item in data.get("items", []):
            body = {
                "datasetName": name,
                "input": item["input"],
                "expectedOutput": item["expected"],
                "metadata": {"id": item["id"]},
                "id": item["id"],
            }
            r = client.post("/api/public/dataset-items", json=body)
            print(f"  item {item['id']}: {r.status_code}")

        r = client.get("/api/public/dataset-items", params={"datasetName": name})
        n = len(r.json().get("data", [])) if r.is_success else 0
        print(f"dataset {name}: {n} items @ {host}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
