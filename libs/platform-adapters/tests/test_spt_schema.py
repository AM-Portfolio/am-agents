"""Validate catalog/spt YAML against target.schema.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3] / "catalog" / "spt"


def test_all_catalog_entries_match_schema() -> None:
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")
    schema = json.loads((ROOT / "target.schema.json").read_text(encoding="utf-8"))
    files = list((ROOT / "services").glob("*.yaml")) + list((ROOT / "flows").glob("*.yaml"))
    assert files, "expected lab catalog entries"
    for path in files:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        jsonschema.validate(instance=data, schema=schema)
