from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
K6_SCRIPT = ROOT / "k6" / "smoke-get.js"
PLAYWRIGHT_SCRIPT = ROOT / "playwright" / "smoke-navigate.spec.ts"


def read_text(path: Path) -> str:
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return f"# missing: {path}"


def sample_payloads() -> dict:
    return {
        "k6_import": {
            "source": "k6",
            "filename": "smoke-get.js",
            "content": read_text(K6_SCRIPT),
            "env": {"POC_TARGET_URL": "{{ poc_target_url }}"},
        },
        "playwright_import": {
            "source": "playwright",
            "filename": "smoke-navigate.spec.ts",
            "content": read_text(PLAYWRIGHT_SCRIPT),
        },
        "bench_run": {
            "vus": 5,
            "duration": "1m",
            "virtualUserId": "{{ virtual_user_id }}",
            "projectId": "{{ project_id }}",
        },
        "har_stub": {
            "log": {
                "version": "1.2",
                "creator": {"name": "spt-poc", "version": "0.1"},
                "entries": [
                    {
                        "request": {
                            "method": "GET",
                            "url": "{{ poc_target_url }}",
                            "headers": [],
                        },
                        "response": {"status": 200, "headers": []},
                    }
                ],
            }
        },
    }


def scripts_bundle() -> dict:
    return {
        "k6": {"path": str(K6_SCRIPT.relative_to(ROOT)), "content": read_text(K6_SCRIPT)},
        "playwright": {
            "path": str(PLAYWRIGHT_SCRIPT.relative_to(ROOT)),
            "content": read_text(PLAYWRIGHT_SCRIPT),
        },
        "payloads": sample_payloads(),
        "payloads_json": json.dumps(sample_payloads(), indent=2),
    }
