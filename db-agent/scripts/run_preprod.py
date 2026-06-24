#!/usr/bin/env python3
"""Run db-agent locally with .env.preprod (used by npm run preprod)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREPROD_ENV = ROOT / ".env.preprod"


def load_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def main() -> int:
    if not PREPROD_ENV.is_file():
        print(f"Missing {PREPROD_ENV}", file=sys.stderr)
        return 1

    env = os.environ.copy()
    env.update(load_env_file(PREPROD_ENV))
    env["APP_ENV"] = "preprod"
    env["ENV_FILE_PATH"] = str(PREPROD_ENV)

    port = env.get("APP_PORT", "8140")
    print(f">>> LLM_ROUTING={env.get('LLM_ROUTING')} gateway={env.get('MCP_GATEWAY_BASE_URL')}", flush=True)
    args = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        str(port),
        "--reload",
    ]
    print(f"\n>>> db-agent preprod on :{port}\n>>> {' '.join(args)}\n", flush=True)
    return subprocess.run(args, cwd=ROOT, env=env).returncode


if __name__ == "__main__":
    raise SystemExit(main())
