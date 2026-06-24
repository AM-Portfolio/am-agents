#!/usr/bin/env python3
"""Scaffold a new tool integration from tools/_template/."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = AGENT_ROOT / "tools" / "_template"
TOOLS_DIR = AGENT_ROOT / "tools"
TOOLS_MD = AGENT_ROOT / "docs" / "TOOLS.md"


def _snake(name: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", name.lower().replace("-", "_"))


def _env_prefix(name: str) -> str:
    return f"{name.upper().replace('-', '_')}_"


def _replace_placeholders(path: Path, mapping: dict[str, str]) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    for key, value in mapping.items():
        text = text.replace(key, value)
    path.write_text(text, encoding="utf-8")


def _walk_replace(root: Path, mapping: dict[str, str]) -> None:
    text_suffixes = {".py", ".yaml", ".yml", ".md", ".txt", ".json"}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in text_suffixes:
            continue
        _replace_placeholders(path, mapping)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a new tool-agent integration")
    parser.add_argument("name", help="Tool folder name (e.g. mongodb)")
    parser.add_argument("--display-name", default=None)
    parser.add_argument("--keywords", default="", help="Comma-separated infer keywords")
    parser.add_argument("--mcp-server", default="toolbox")
    parser.add_argument("--has-entities", action="store_true")
    parser.add_argument("--enable", action="store_true", help="Set manifest enabled: true")
    args = parser.parse_args()

    name = _snake(args.name)
    target = TOOLS_DIR / name
    if target.exists():
        print(f"ERROR: {target} already exists", file=sys.stderr)
        return 1

    display = args.display_name or name.replace("_", " ").title()
    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()] or [name]
    mapping = {
        "__TOOL_NAME__": name,
        "__DISPLAY_NAME__": display,
        "__KEYWORDS__": ", ".join(keywords),
        "__ENV_PREFIX__": _env_prefix(name),
    }

    shutil.copytree(
        TEMPLATE_DIR,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
    )
    _walk_replace(target, mapping)

    manifest = target / "manifest.yaml"
    text = manifest.read_text(encoding="utf-8")
    text = text.replace("supports_mcp: false", f"supports_mcp: {str(args.mcp_server != 'none').lower()}")
    text = text.replace("mcp_server: toolbox", f"mcp_server: {args.mcp_server}")
    text = text.replace("has_entities: false", f"has_entities: {str(args.has_entities).lower()}")
    if args.enable:
        text = text.replace("enabled: false", "enabled: true")
    manifest.write_text(text, encoding="utf-8")

    TOOLS_MD.parent.mkdir(parents=True, exist_ok=True)
    line = f"- [{display}](tools/{name}/README.md) — `{name}`\n"
    if TOOLS_MD.exists():
        content = TOOLS_MD.read_text(encoding="utf-8")
        if line not in content:
            TOOLS_MD.write_text(content + line, encoding="utf-8")
    else:
        TOOLS_MD.write_text("# Tool integrations\n\n" + line, encoding="utf-8")

    print(f"Created {target}")
    print("Next: implement adapter.py, registry.yaml operations, search/, prompts/")
    print(f"Validate: python scripts/validate_tool.py {name}")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(target / "tests"), "-q"],
        cwd=AGENT_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print("Stub tests: PASS")
    else:
        print("Stub tests: FAIL")
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
