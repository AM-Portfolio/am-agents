"""Ensure worker/ports sources do not hardcode catalog target ids."""

from __future__ import annotations

from pathlib import Path

FORBIDDEN = ("tgt-a", "tgt-b", "tgt-c", "flow-lab-1", "prep.shared-lab")


def test_no_catalog_ids_in_worker_or_ports() -> None:
    roots = [
        Path(__file__).resolve().parents[3] / "platform_worker" / "src",
        Path(__file__).resolve().parents[2] / "platform-ports" / "src",
    ]
    hits: list[str] = []
    for root in roots:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for token in FORBIDDEN:
                if token in text:
                    hits.append(f"{path}:{token}")
    assert hits == [], f"catalog ids leaked into code: {hits}"
