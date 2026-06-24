"""Register db-agent MCP servers with LiteLLM Management API (Phase 2c)."""
from __future__ import annotations

import argparse
import os

import httpx

ALIASES = ["db_toolbox", "db_qdrant", "db_kafka", "db_grafana"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync db-agent MCP servers to LiteLLM")
    parser.add_argument("--base-url", default=os.getenv("LITELLM_BASE_URL", "http://localhost:4000"))
    parser.add_argument("--master-key", default=os.getenv("LITELLM_MASTER_KEY", ""))
    args = parser.parse_args()

    if not args.master_key:
        raise SystemExit("LITELLM_MASTER_KEY required")

    headers = {"Authorization": f"Bearer {args.master_key}"}
    with httpx.Client(base_url=args.base_url.rstrip("/"), headers=headers, timeout=30) as client:
        existing = client.get("/v1/mcp/server")
        print("Current MCP servers:", existing.json())
        for alias in ALIASES:
            print(f"Register {alias} — configure transport in LiteLLM UI or extend this script")


if __name__ == "__main__":
    main()
