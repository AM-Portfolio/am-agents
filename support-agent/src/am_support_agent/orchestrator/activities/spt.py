"""SPT activities — catalog resolve + capability-backed execute when parity on."""

from __future__ import annotations

import os
from typing import Any

from temporalio import activity

from am_support_agent.adapters.security import SandboxPolicy
from am_support_agent.composition import build_runtime
from am_support_agent.contracts.capabilities import (
    ApprovalMetadata,
    CapabilityCall,
    IdempotencyMetadata,
)
from am_support_agent.contracts.enums import ApprovalRisk
from am_support_agent.intelligence.catalog import CatalogReader


def spt_parity_enabled() -> bool:
    return os.getenv("SUPPORT_AGENT_SPT_PARITY", "").lower() in {
        "1",
        "true",
        "yes",
    }


def _gate_payload(phase: str, demand_ref: str) -> dict[str, Any]:
    return {
        "gated": True,
        "phase": phase,
        "demand_ref": demand_ref,
        "module": "support-agent",
        "task_queue": "support-agent-v2",
        "reason": (
            "SPT fan-out / child execution is gated until "
            "SUPPORT_AGENT_SPT_PARITY=true."
        ),
        "legacy_reference": "platform_worker/src/platform_worker/workflows/spt_run.py",
    }


@activity.defn(name="support_agent.spt.resolve_catalog")
async def resolve_spt_catalog(payload: dict[str, Any]) -> dict[str, Any]:
    """Read-only catalog listing — safe without SPT parity flag."""
    demand = dict(payload.get("demand") or {})
    demand_ref = str(
        demand.get("demand_ref") or payload.get("demand_ref") or payload.get("run_ref") or ""
    )
    reader = CatalogReader.from_env()
    entries = reader.list_spt()
    return {
        "gated": False,
        "phase": "resolve_catalog",
        "demand_ref": demand_ref,
        "catalog_root": str(reader.root),
        "spt_entry_count": len(entries),
        "spt_ids": [e.get("id") or e.get("name") for e in entries[:50]],
        "demand": demand,
    }


@activity.defn(name="support_agent.spt.bootstrap")
async def bootstrap_spt(payload: dict[str, Any]) -> dict[str, Any]:
    demand = dict(payload.get("demand") or {})
    demand_ref = str(
        demand.get("demand_ref") or payload.get("demand_ref") or payload.get("run_ref") or ""
    )
    catalog = await resolve_spt_catalog(payload)
    if not spt_parity_enabled():
        gated = _gate_payload("bootstrap", demand_ref)
        gated["catalog_preview"] = {
            "spt_entry_count": catalog.get("spt_entry_count"),
            "catalog_root": catalog.get("catalog_root"),
        }
        return gated

    sandbox = bool(demand.get("sandbox", True))
    allowed, reason = SandboxPolicy().allow_spt(sandbox=sandbox)
    if not allowed:
        return {
            "gated": True,
            "phase": "bootstrap",
            "demand_ref": demand_ref,
            "reason": reason,
            "catalog": catalog,
        }

    runtime = build_runtime()
    prep = await runtime.capability.call(
        CapabilityCall(
            capability="spt.test-data.prepare",
            args={"demand_ref": demand_ref, **{k: v for k, v in demand.items() if k != "sandbox"}},
            approval=ApprovalMetadata(risk=ApprovalRisk.CREATE),
            idempotency=IdempotencyMetadata(key=f"{demand_ref}:prep"),
        )
    )
    exe = await runtime.capability.call(
        CapabilityCall(
            capability="spt.execute",
            args={
                "demand_ref": demand_ref,
                "sandbox": sandbox,
                "prep_ref": (prep.data or {}).get("prep_ref"),
            },
            approval=ApprovalMetadata(risk=ApprovalRisk.EXECUTE),
            idempotency=IdempotencyMetadata(key=f"{demand_ref}:exec"),
        )
    )
    status = await runtime.capability.call(
        CapabilityCall(
            capability="spt.status",
            args={
                "async_operation_ref": (exe.data or {}).get("async_operation_ref")
                or (exe.data or {}).get("run_ref")
                or ""
            },
        )
    )
    return {
        "gated": False,
        "phase": "bootstrap",
        "demand_ref": demand_ref,
        "catalog": catalog,
        "prep": prep.model_dump(),
        "execute": exe.model_dump(),
        "status": status.model_dump(),
        "sandbox": sandbox,
    }
