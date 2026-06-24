#!/usr/bin/env python3
"""Upsert tool-agent prompts from tools/*/prompts/*.yaml into Langfuse."""

from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

import httpx
import yaml

AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AGENT_ROOT))

from app.config import settings  # noqa: E402
from tools._shared.text import load_yaml_text  # noqa: E402


def _auth() -> str | None:
    if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        return None
    token = f"{settings.LANGFUSE_PUBLIC_KEY}:{settings.LANGFUSE_SECRET_KEY}"
    return base64.b64encode(token.encode()).decode()


def upsert_prompt(name: str, content: str, *, dry_run: bool) -> None:
    if dry_run:
        print(f"DRY RUN upsert {name} ({len(content)} chars)")
        return
    auth = _auth()
    if not auth:
        raise SystemExit("LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY required")
    host = settings.LANGFUSE_HOST.rstrip("/")
    resp = httpx.post(
        f"{host}/api/public/v2/prompts",
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
        json={"name": name, "prompt": content, "labels": ["latest"]},
        timeout=30.0,
    )
    if resp.status_code not in (200, 201):
        raise SystemExit(f"Langfuse upsert failed for {name}: [{resp.status_code}] {resp.text[:300]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    base_path = AGENT_ROOT / "app" / "prompts" / "base.yaml"
    upsert_prompt("tool-agent/intent/base", load_yaml_text(base_path), dry_run=args.dry_run)

    tools_dir = AGENT_ROOT / "tools"
    for tool_dir in sorted(tools_dir.iterdir()):
        if not tool_dir.is_dir() or tool_dir.name.startswith("_"):
            continue
        for prompt_file in ("intent.yaml", "examples.yaml"):
            path = tool_dir / "prompts" / prompt_file
            if not path.exists():
                continue
            suffix = "examples" if prompt_file == "examples.yaml" else ""
            name = f"tool-agent/intent/{tool_dir.name}" + (f"/{suffix}" if suffix else "")
            upsert_prompt(name, load_yaml_text(path), dry_run=args.dry_run)
            print(f"Synced {name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
