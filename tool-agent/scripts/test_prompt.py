#!/usr/bin/env python3
"""Reload and preview Langfuse/file prompts against a running tool-agent (no restart)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AGENT_ROOT))

from app.config import settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=f"http://127.0.0.1:{settings.APP_PORT}",
        help="Running tool-agent base URL",
    )
    parser.add_argument("--reload", action="store_true", help="POST /api/v1/prompts/reload first")
    parser.add_argument("--cache", action="store_true", help="GET /api/v1/prompts/cache")
    parser.add_argument("--name", help="Prompt name, e.g. tool-agent/intent/grafana")
    parser.add_argument("--label", help="Langfuse label (default: APP_ENV mapping)")
    parser.add_argument("--fallback", help="Relative fallback path for file mode")
    parser.add_argument("--query", help="Build full intent prompt for this query")
    parser.add_argument("--backend", help="Backend hint for --query")
    parser.add_argument("--god-mode", action="store_true")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    with httpx.Client(timeout=30.0) as client:
        if args.reload:
            resp = client.post(f"{base}/api/v1/prompts/reload")
            print(f"reload [{resp.status_code}] {resp.text}")
            if resp.status_code >= 400:
                return 1

        if args.cache:
            resp = client.get(f"{base}/api/v1/prompts/cache")
            print(json.dumps(resp.json(), indent=2))
            if resp.status_code >= 400:
                return 1
            if not args.name and not args.query:
                return 0

        if not args.name and not args.query:
            parser.error("provide --name and/or --query (or only --cache/--reload)")

        body: dict = {}
        if args.name:
            body["name"] = args.name
            if args.label:
                body["label"] = args.label
            if args.fallback:
                body["fallback"] = args.fallback
        if args.query:
            body["query"] = args.query
            if args.backend:
                body["backend"] = args.backend
            body["god_mode"] = args.god_mode

        resp = client.post(f"{base}/api/v1/prompts/preview", json=body)
        if resp.status_code >= 400:
            print(f"preview failed [{resp.status_code}] {resp.text}", file=sys.stderr)
            return 1
        data = resp.json()
        if "prompt" in data:
            print(f"source={data.get('prompt_source')} label={data.get('label')} candidates={data.get('candidates')}")
            for snip in data.get("snippets") or []:
                print(
                    f"  - {snip.get('name')} source={snip.get('source')} "
                    f"version={snip.get('version')} chars={snip.get('chars')}"
                )
            print("---")
            print(data["prompt"])
        else:
            print(
                f"name={data.get('name')} source={data.get('source')} "
                f"version={data.get('version')} label={data.get('label')} "
                f"age={data.get('age_seconds')}"
            )
            print("---")
            print(data.get("content") or "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
