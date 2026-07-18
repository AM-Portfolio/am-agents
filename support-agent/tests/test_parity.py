"""Legacy/replacement parity comparator tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from am_support_agent.parity import (
    SHADOW_MATCH_THRESHOLD,
    SOFT_MATCH_THRESHOLD,
    compare_results,
    meets_parity_threshold,
)

FIXTURES = Path(__file__).parent / "fixtures" / "parity"


def test_parity_ignores_volatile_ids_and_latency():
    legacy = {
        "task_id": "old",
        "status": "succeeded",
        "data": {"steps": ["inspect", "verify"]},
        "metrics": {"latency_ms": 100, "cost_units": 1},
    }
    replacement = {
        "task_id": "new",
        "status": "succeeded",
        "data": {"steps": ["inspect", "verify"]},
        "metrics": {"latency_ms": 5, "cost_units": 1},
    }
    report = compare_results(legacy, replacement)
    assert report.matched
    assert report.meets_threshold
    assert report.match_rate == 1.0
    assert report.compared_fields >= 3


def test_parity_reports_path_and_values():
    report = compare_results(
        {"status": "succeeded", "data": {"decision": "route"}},
        {"status": "failed", "data": {"decision": "escalate"}},
    )
    assert not report.matched
    assert not report.meets_threshold
    paths = {difference.path for difference in report.differences}
    assert paths == {"status", "data.decision"}


def test_soft_threshold_allows_partial_match_rate():
    soft = compare_results(
        {
            "a": 1,
            "b": 2,
            "c": 3,
            "d": 4,
            "e": 5,
            "f": 6,
            "g": 7,
            "h": 8,
            "i": 9,
            "j": 10,
            "k": 11,
            "l": 12,
            "m": 13,
            "n": 14,
            "o": 15,
            "p": 16,
            "q": 17,
            "r": 18,
            "s": 19,
            "t": 20,
        },
        {
            "a": 1,
            "b": 2,
            "c": 3,
            "d": 4,
            "e": 5,
            "f": 6,
            "g": 7,
            "h": 8,
            "i": 9,
            "j": 10,
            "k": 11,
            "l": 12,
            "m": 13,
            "n": 14,
            "o": 15,
            "p": 16,
            "q": 17,
            "r": 18,
            "s": 19,
            "t": 99,
        },
        threshold=SOFT_MATCH_THRESHOLD,
    )
    assert not soft.matched
    assert soft.match_rate == 0.95
    assert soft.meets_threshold
    assert meets_parity_threshold(soft, threshold=SOFT_MATCH_THRESHOLD)
    assert not meets_parity_threshold(soft, threshold=SHADOW_MATCH_THRESHOLD)


def _fixture_cases() -> list[tuple[str, dict]]:
    files = sorted(FIXTURES.glob("*.json"))
    assert files, f"expected parity fixtures under {FIXTURES}"
    return [(path.stem, json.loads(path.read_text(encoding="utf-8"))) for path in files]


@pytest.mark.parametrize(
    "name,fixture",
    _fixture_cases(),
    ids=[name for name, _ in _fixture_cases()],
)
def test_parity_fixtures(name: str, fixture: dict):
    assert fixture.get("name")
    report = compare_results(fixture["legacy"], fixture["replacement"])
    assert report.matched is fixture["expect_matched"]
    assert report.meets_threshold is fixture["expect_matched"]
    if not fixture["expect_matched"]:
        expected = set(fixture.get("expected_paths") or [])
        if expected:
            paths = {difference.path for difference in report.differences}
            assert expected <= paths
