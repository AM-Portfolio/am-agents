"""Deterministic legacy-vs-replacement comparison for shadow traffic."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


DEFAULT_IGNORED_KEYS = {
    "task_id",
    "run_id",
    "workflow_id",
    "created_at",
    "updated_at",
    "latency_ms",
}

# Shadow discover/plan must match exactly after ignored keys.
SHADOW_MATCH_THRESHOLD = 1.0
# Soft floor for experimental non-shadow scorers (not used by /v2/shadow).
SOFT_MATCH_THRESHOLD = 0.95


class ParityDifference(BaseModel):
    path: str
    legacy: Any = None
    replacement: Any = None
    reason: str


class ParityReport(BaseModel):
    matched: bool
    differences: list[ParityDifference] = Field(default_factory=list)
    compared_fields: int = 0
    matched_fields: int = 0
    match_rate: float = 1.0
    ignored_keys: list[str] = Field(default_factory=list)
    threshold: float = SHADOW_MATCH_THRESHOLD
    meets_threshold: bool = True


def compare_results(
    legacy: dict[str, Any],
    replacement: dict[str, Any],
    *,
    ignored_keys: set[str] | None = None,
    threshold: float = SHADOW_MATCH_THRESHOLD,
) -> ParityReport:
    ignored = ignored_keys or DEFAULT_IGNORED_KEYS
    differences: list[ParityDifference] = []
    compared = 0
    matched_fields = 0

    def walk(old: Any, new: Any, path: str) -> None:
        nonlocal compared, matched_fields
        if isinstance(old, dict) and isinstance(new, dict):
            keys = (set(old) | set(new)) - ignored
            for key in sorted(keys):
                child = f"{path}.{key}" if path else key
                if key not in old:
                    compared += 1
                    differences.append(
                        ParityDifference(
                            path=child,
                            replacement=new[key],
                            reason="missing_in_legacy",
                        )
                    )
                elif key not in new:
                    compared += 1
                    differences.append(
                        ParityDifference(
                            path=child,
                            legacy=old[key],
                            reason="missing_in_replacement",
                        )
                    )
                else:
                    walk(old[key], new[key], child)
            return
        if isinstance(old, list) and isinstance(new, list):
            compared += 1
            if old != new:
                differences.append(
                    ParityDifference(
                        path=path,
                        legacy=old,
                        replacement=new,
                        reason="list_mismatch",
                    )
                )
            else:
                matched_fields += 1
            return
        compared += 1
        if old != new:
            differences.append(
                ParityDifference(
                    path=path,
                    legacy=old,
                    replacement=new,
                    reason="value_mismatch",
                )
            )
        else:
            matched_fields += 1

    walk(legacy, replacement, "")
    match_rate = 1.0 if compared == 0 else matched_fields / compared
    matched = not differences
    meets = matched if threshold >= 1.0 else match_rate >= threshold
    return ParityReport(
        matched=matched,
        differences=differences,
        compared_fields=compared,
        matched_fields=matched_fields,
        match_rate=match_rate,
        ignored_keys=sorted(ignored),
        threshold=threshold,
        meets_threshold=meets,
    )


def meets_parity_threshold(
    report: ParityReport, *, threshold: float | None = None
) -> bool:
    floor = SHADOW_MATCH_THRESHOLD if threshold is None else threshold
    if floor >= 1.0:
        return report.matched
    return report.match_rate >= floor
