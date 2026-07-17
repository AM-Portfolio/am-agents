"""TargetResolver + LoadPolicy + DataPrep + LoadTestRunner (lab)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from typing import Any

from am_platform_ports.schemas.spt import SptDemandRequest, SptSelector

from am_platform_adapters.providers.spt.catalog import FileTargetCatalog

LOG = logging.getLogger("am_platform_adapters.spt")


def _selector_hash(selector: SptSelector) -> str:
    raw = json.dumps(selector.model_dump(), sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class CatalogTargetResolver:
    def __init__(self, catalog: FileTargetCatalog | None = None) -> None:
        self._catalog = catalog or FileTargetCatalog()

    def resolve(self, *, selector: SptSelector) -> list[str]:
        entries = self._catalog.list_all()
        max_targets = int(os.getenv("SPT_MAX_TARGETS_PER_RUN", "20"))
        env = os.getenv("SPT_ENV", "lab").strip().lower()
        sel_hash = _selector_hash(selector)

        if selector.all:
            if env != "lab":
                raise PermissionError("selector.all only allowed in lab")
            if os.getenv("SPT_ALLOW_ALL", "").strip() not in {"1", "true", "yes"}:
                raise PermissionError("selector.all requires SPT_ALLOW_ALL=1 + Approve in lab")
            # Prod catalog defaults enabled:false; lab entries opt in with enabled:true
            ids = [e["id"] for e in entries if e.get("enabled", False)]
        else:
            ids_set: set[str] = set()
            if selector.ids:
                ids_set.update(selector.ids)
            if selector.tags:
                tagset = set(selector.tags)
                for e in entries:
                    if tagset.intersection(set(e.get("tags") or [])):
                        ids_set.add(e["id"])
            ids = sorted(ids_set)

        expanded = len(ids)
        LOG.info(
            "spt.resolve selector_hash=%s expanded_count=%s max=%s env=%s all=%s",
            sel_hash,
            expanded,
            max_targets,
            env,
            bool(selector.all),
        )
        if expanded > max_targets:
            LOG.error(
                "spt.resolve ALERT expansion=%s exceeds SPT_MAX_TARGETS_PER_RUN=%s selector_hash=%s",
                expanded,
                max_targets,
                sel_hash,
            )
            raise PermissionError(
                f"expanded_count={expanded} exceeds SPT_MAX_TARGETS_PER_RUN={max_targets}"
            )
        if not ids:
            raise ValueError("empty TargetSet after resolve — fatal")
        # Ensure all exist
        for tid in ids:
            if self._catalog.get(target_id=tid) is None:
                raise KeyError(f"unknown target_id: {tid}")
        return ids


class LabLoadPolicy:
    """Lab: catalog `enabled` flag only."""

    def allow(self, *, target_ref: str, request: SptDemandRequest) -> bool:
        _ = request
        cat = FileTargetCatalog()
        entry = cat.get(target_id=target_ref)
        if entry is None:
            return False
        return bool(entry.get("enabled", False))


class ProdLoadPolicy:
    """Prod: enabled + Approve + change window; observe/doc mandatory at workflow layer."""

    def allow(self, *, target_ref: str, request: SptDemandRequest) -> bool:
        _ = request
        cat = FileTargetCatalog()
        entry = cat.get(target_id=target_ref)
        if entry is None or not bool(entry.get("enabled", False)):
            return False
        if os.getenv("SPT_APPROVED", "").strip() not in {"1", "true", "yes"}:
            return False
        if os.getenv("SPT_CHANGE_WINDOW_OPEN", "").strip() not in {"1", "true", "yes"}:
            return False
        return True


class DedupeDataPrep:
    """ensure_dataset once per prep_ref per parent run."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], str] = {}

    def ensure_dataset(self, *, prep_ref: str, parent_run_ref: str | None = None) -> str:
        key = (parent_run_ref or "_", prep_ref)
        if key in self._cache:
            return self._cache[key]
        dataset_ref = f"dataset-{hashlib.sha1(f'{key}'.encode()).hexdigest()[:12]}"
        self._cache[key] = dataset_ref
        return dataset_ref


class SandboxLoadTestRunner:
    """Runs scenario via ToolSandbox allowlisted lab.k6 tool."""

    def __init__(self, sandbox: Any | None = None) -> None:
        if sandbox is None:
            from am_platform_ports.fakes import FakeToolSandbox

            # extend allowlist for SPT
            class _Sb(FakeToolSandbox):
                ALLOWLIST = frozenset({"lab.noop", "lab.mark_fixed", "lab.k6", "lab.prep"})

            sandbox = _Sb()
        self._sandbox = sandbox

    def run(
        self,
        *,
        scenario_ref: str,
        base_url_secret_ref: str,
        dataset_ref: str | None = None,
        target_ref: str | None = None,
    ) -> str:
        force_fail = os.getenv("SPT_FORCE_FAIL_TARGET", "").strip()
        if target_ref and force_fail and target_ref == force_fail:
            raise RuntimeError(f"forced fail for target {target_ref}")
        out = self._sandbox.run(
            tool_name="lab.k6",
            args={
                "scenario_ref": scenario_ref,
                "base_url_secret_ref": base_url_secret_ref,
                "dataset_ref": dataset_ref,
                "target_ref": target_ref,
            },
        )
        return f"load-{uuid.uuid4().hex[:12]}" if out.get("ok") else f"load-fail-{uuid.uuid4().hex[:8]}"
