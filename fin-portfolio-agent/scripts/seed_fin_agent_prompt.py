#!/usr/bin/env python3
"""
Seed Langfuse prompt fin-agent/system from prompts/fin_agent_system.md.

Requires LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST.
Creates/updates prompt; does not flip production labels (use Langfuse UI).

  python scripts/seed_fin_agent_prompt.py --label dev
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPT_FILE = ROOT / "prompts" / "fin_agent_system.md"
PROMPT_NAME = "fin-agent/system"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default=os.getenv("PROMPT_LABEL", "dev"))
    parser.add_argument("--name", default=PROMPT_NAME)
    args = parser.parse_args()

    pk = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    sk = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    host = os.getenv("LANGFUSE_HOST", "https://langfuse.munish.org").rstrip("/")
    if not pk or not sk:
        print("LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY required", file=sys.stderr)
        return 2
    if not PROMPT_FILE.exists():
        print(f"Missing {PROMPT_FILE}", file=sys.stderr)
        return 2

    content = PROMPT_FILE.read_text(encoding="utf-8").strip()
    try:
        from langfuse import Langfuse
    except ImportError:
        print("Install langfuse: pip install langfuse", file=sys.stderr)
        return 2

    client = Langfuse(public_key=pk, secret_key=sk, host=host)
    # create_prompt API varies by SDK version
    try:
        client.create_prompt(
            name=args.name,
            prompt=content,
            labels=[args.label],
            type="text",
        )
    except TypeError:
        client.create_prompt(
            name=args.name,
            prompt=content,
            labels=[args.label],
        )
    print(f"Seeded {args.name} label={args.label} ({len(content)} chars) -> {host}")
    try:
        client.flush()
    except Exception:  # noqa: BLE001
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
