#!/usr/bin/env python3
"""Validate a tool folder implements the IntegrationTool contract."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import yaml

AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AGENT_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("name", help="Tool name (folder under tools/)")
    args = parser.parse_args()

    tool_dir = AGENT_ROOT / "tools" / args.name
    if not tool_dir.exists():
        print(f"ERROR: missing {tool_dir}", file=sys.stderr)
        return 1

    manifest_path = tool_dir / "manifest.yaml"
    registry_path = tool_dir / "registry.yaml"
    plugin_path = tool_dir / "plugin.py"
    intent_path = tool_dir / "prompts" / "intent.yaml"

    for path in (manifest_path, registry_path, plugin_path, intent_path):
        if not path.exists():
            print(f"ERROR: missing required file {path}", file=sys.stderr)
            return 1

    with manifest_path.open(encoding="utf-8") as f:
        manifest = yaml.safe_load(f) or {}
    with registry_path.open(encoding="utf-8") as f:
        registry = yaml.safe_load(f) or {}

    spec = importlib.util.spec_from_file_location(f"tools_{args.name}_plugin", plugin_path)
    if not spec or not spec.loader:
        print("ERROR: could not load plugin.py", file=sys.stderr)
        return 1
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    factory = getattr(module, "get_tool", None)
    if not callable(factory):
        print("ERROR: plugin.py must export get_tool()", file=sys.stderr)
        return 1
    tool = factory()

    ops = (registry.get("operations") or {}).keys()
    tool_ops = set(tool.operations())
    if set(ops) != tool_ops:
        print(f"ERROR: registry operations {set(ops)} != tool.operations() {tool_ops}", file=sys.stderr)
        return 1

    print(f"OK: {args.name} manifest={manifest.get('name')} enabled={manifest.get('enabled')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
