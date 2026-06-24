#!/usr/bin/env python3
"""Start ui-test-agent with ENV_FILE_PATH set (cross-platform npm script helper)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    args = sys.argv[1:]
    reload = False
    if "--reload" in args:
        reload = True
        args.remove("--reload")

    env_file = args[0] if args else ".env.preprod"
    os.environ["ENV_FILE_PATH"] = env_file
    os.chdir(ROOT)

    port = os.environ.get("APP_PORT", "8130")
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        port,
    ]
    if reload:
        cmd.append("--reload")

    print(f"ENV_FILE_PATH={env_file}  port={port}", flush=True)
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
