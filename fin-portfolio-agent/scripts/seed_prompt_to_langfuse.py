#!/usr/bin/env python3
"""Upsert fin-agent/finance-system prompt from shared/prompts/system.py into Langfuse."""

from __future__ import annotations

import argparse
import base64
import os
import sys
from pathlib import Path

import httpx

AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AGENT_ROOT))

from shared.core.config import settings  # noqa: E402
from shared.prompts.system import (  # noqa: E402
    LANGFUSE_PROMPT_NAME,
    PROMPT_VERSION,
    get_system_prompt,
)


def _load_creds() -> tuple[str, str, str]:
    """Load Langfuse host + keys from env or ~/.asrax / ~/.am credential files."""
    keys = ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
    found: dict[str, str] = {}
    for key in keys:
        val = os.environ.get(key, "").strip()
        if val:
            found[key] = val
    roots = [Path.home() / ".asrax", Path.home() / ".am"]
    files: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        files.extend(
            [
                root / "credentials.env",
                root / "credentials.vault.env",
                root / "asrax.prod.env",
            ]
        )
        cred_d = root / "credentials.d"
        if cred_d.is_dir():
            files.extend(sorted(cred_d.glob("*")))
    for path in files:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k in keys and v and k not in found:
                found[k] = v
    host = (found.get("LANGFUSE_HOST") or settings.LANGFUSE_HOST or "https://langfuse.munish.org").rstrip("/")
    pk = found.get("LANGFUSE_PUBLIC_KEY") or settings.LANGFUSE_PUBLIC_KEY
    sk = found.get("LANGFUSE_SECRET_KEY") or settings.LANGFUSE_SECRET_KEY
    if not pk or not sk:
        raise SystemExit(
            "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY required "
            "(env, ~/.asrax/credentials.env, or fin-agent Vault keys)"
        )
    return host, pk, sk


def upsert_prompt(*, labels: list[str], dry_run: bool) -> None:
    content = get_system_prompt(enable_portfolio=True)
    name = LANGFUSE_PROMPT_NAME
    print(f"Prompt: {name} v{PROMPT_VERSION} ({len(content)} chars)")
    print(f"Labels: {labels}")
    if dry_run:
        print("DRY RUN — first 400 chars:")
        print(content[:400])
        print("...")
        return

    host, pk, sk = _load_creds()
    auth = base64.b64encode(f"{pk}:{sk}".encode()).decode()
    resp = httpx.post(
        f"{host}/api/public/v2/prompts",
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
        json={
            "name": name,
            "prompt": content,
            "labels": labels,
            "config": {"version": PROMPT_VERSION, "promptId": "fin-agent-system-v1"},
        },
        timeout=30.0,
    )
    if resp.status_code not in (200, 201):
        raise SystemExit(f"Langfuse upsert failed [{resp.status_code}]: {resp.text[:400]}")
    data = resp.json()
    version = data.get("version") or data.get("promptVersion") or "?"
    print(f"OK: upserted {name} version={version} host={host}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed fin-agent finance-system prompt to Langfuse")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--label",
        action="append",
        default=["prod", "latest"],
        help="Langfuse labels to attach (default: prod + latest)",
    )
    args = parser.parse_args()
    upsert_prompt(labels=args.label, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
