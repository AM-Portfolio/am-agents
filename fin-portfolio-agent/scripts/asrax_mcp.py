"""Exchange an Asrax API key and launch mcp-remote with a short-lived Bearer."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

import httpx


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def main() -> int:
    identity_url = os.getenv(
        "ASRAX_IDENTITY_URL", "https://am.asrax.in/identity"
    ).rstrip("/")
    mcp_url = os.getenv("ASRAX_MCP_URL", "https://am.asrax.in/ai/mcp")
    response = httpx.post(
        f"{identity_url}/auth/api-key",
        json={
            "key_id": required("ASRAX_KEY_ID"),
            "secret": required("ASRAX_KEY_SECRET"),
        },
        timeout=15.0,
    )
    response.raise_for_status()
    access_token = response.json()["access_token"]

    env = {**os.environ, "ASRAX_MCP_AUTH_HEADER": f"Bearer {access_token}"}
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        raise RuntimeError("npx is required to run mcp-remote")
    return subprocess.call(
        [
            npx,
            "-y",
            "mcp-remote",
            mcp_url,
            "--header",
            "Authorization:${ASRAX_MCP_AUTH_HEADER}",
        ],
        env=env,
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"asrax-mcp: {exc}", file=sys.stderr)
        raise SystemExit(1)
