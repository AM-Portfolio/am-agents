#!/usr/bin/env python3
"""Validate am.spt/v1 ServiceLoadTest YAML (minimal registration)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REQUIRED = ("apiVersion", "kind", "service", "runtime", "targets")
ALLOWED_RUNTIME = {"java", "python", "fastapi", "spring"}


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return [f"{path}: parse error: {exc}"]
    if not isinstance(data, dict):
        return [f"{path}: root must be a mapping"]
    for key in REQUIRED:
        if key not in data:
            errors.append(f"{path}: missing '{key}'")
    if data.get("apiVersion") != "am.spt/v1":
        errors.append(f"{path}: apiVersion must be am.spt/v1")
    if data.get("kind") != "ServiceLoadTest":
        errors.append(f"{path}: kind must be ServiceLoadTest")
    runtime = str(data.get("runtime") or "").lower()
    if runtime and runtime not in ALLOWED_RUNTIME:
        errors.append(f"{path}: runtime must be one of {sorted(ALLOWED_RUNTIME)}")
    targets = data.get("targets")
    if not isinstance(targets, dict) or not targets:
        errors.append(f"{path}: targets must be a non-empty map (dev/preprod/prod)")
    else:
        if "dev" not in targets:
            errors.append(f"{path}: targets.dev is required")
        for env, url in targets.items():
            if env.startswith("public_"):
                continue
            if not isinstance(url, str) or not url.startswith("http"):
                errors.append(f"{path}: targets.{env} must be an http(s) URL")
    # Auth and apis lists are intentionally not required (and discouraged)
    if data.get("auth"):
        errors.append(f"{path}: do not set auth — SPT platform owns identity login")
    oas = data.get("openapi")
    if oas is not None and not isinstance(oas, dict):
        errors.append(f"{path}: openapi must be a mapping with optional path")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="spt.yaml files or directories")
    args = parser.parse_args()
    files: list[Path] = []
    for p in args.paths:
        if p.is_dir():
            files.extend(sorted(p.rglob("spt.yaml")))
        else:
            files.append(p)
    if not files:
        print("no spt.yaml files found", file=sys.stderr)
        return 2
    all_errors: list[str] = []
    for f in files:
        errs = validate(f)
        if errs:
            all_errors.extend(errs)
        else:
            print(f"OK {f}")
    if all_errors:
        for e in all_errors:
            print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
