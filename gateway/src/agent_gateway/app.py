"""FastAPI L2 gateway — Start / Signal / status + auth; create_run on Start."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from am_platform_adapters.factory import build_handoff, build_run_store
from am_platform_ports.schemas.enums import RunKind, RunStatus
from am_platform_ports.schemas.run import CreateRunRequest
from am_platform_ports.schemas.spt import SptDemandRequest

from agent_gateway.auth import require_token
from agent_gateway import spt_guard
from agent_gateway import temporal_api as tapi


class AlertStartBody(BaseModel):
    tracking_id: str
    alert: dict[str, Any] = Field(default_factory=dict)


class SptStartBody(BaseModel):
    demand: dict[str, Any]
    workflow_id: str | None = None


class HandoffBody(BaseModel):
    from_run_ref: str
    to_kind: str
    depth: int = 1
    context: dict[str, Any] | None = None


def _selector_hash(selector: dict[str, Any]) -> str:
    raw = json.dumps(selector, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def create_app() -> FastAPI:
    app = FastAPI(title="AM Agent Gateway", version="0.1.0")
    runs = build_run_store()
    handoff = build_handoff(runs)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/workflows/alert-incident")
    async def start_alert(
        body: AlertStartBody,
        _: str = Depends(require_token),
    ) -> dict[str, Any]:
        wid = f"alert-incident-{body.tracking_id}"
        run = runs.create_run(
            CreateRunRequest(
                kind=RunKind.ALERT_INCIDENT,
                status=RunStatus.ACCEPTED,
                incident_ref=body.tracking_id,
                workflow_id=wid,
            )
        )
        try:
            result = await tapi.start_alert_incident(
                workflow_id=wid,
                tracking_id=body.tracking_id,
                alert=body.alert,
                run_ref=run.run_ref,
            )
        except Exception as exc:
            runs.update_run_status(
                run_ref=run.run_ref,
                status=RunStatus.FAILED,
                summary={"error": str(exc)[:200]},
            )
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return result

    @app.post("/v1/workflows/spt")
    async def start_spt(
        body: SptStartBody,
        _: str = Depends(require_token),
    ) -> dict[str, Any]:
        demand_model = SptDemandRequest.model_validate(body.demand)
        demand = demand_model.model_dump()
        wid = body.workflow_id or f"spt-{demand_model.demand_ref}-{uuid.uuid4().hex[:8]}"
        try:
            spt_guard.try_acquire_spt(wid)
        except PermissionError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        run = runs.create_run(
            CreateRunRequest(
                kind=RunKind.SPT,
                status=RunStatus.ACCEPTED,
                demand_ref=demand_model.demand_ref,
                workflow_id=wid,
                requested_selector_hash=_selector_hash(demand_model.selector.model_dump()),
            )
        )
        try:
            result = await tapi.start_spt(workflow_id=wid, demand=demand, run_ref=run.run_ref)
        except Exception as exc:
            spt_guard.release_spt(wid)
            runs.update_run_status(
                run_ref=run.run_ref,
                status=RunStatus.FAILED,
                summary={"error": str(exc)[:200]},
            )
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return result

    @app.post("/v1/workflows/{workflow_id}/signals/{signal_name}")
    async def signal(
        workflow_id: str,
        signal_name: str,
        _: str = Depends(require_token),
    ) -> dict[str, str]:
        allowed = {"approve", "alert.resolved", "alert.refired"}
        if signal_name not in allowed:
            raise HTTPException(status_code=400, detail=f"signal not allowed: {signal_name}")
        try:
            return await tapi.signal_workflow(workflow_id=workflow_id, signal_name=signal_name)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/v1/workflows/{workflow_id}/status")
    async def status(
        workflow_id: str,
        _: str = Depends(require_token),
    ) -> dict[str, Any]:
        try:
            result = await tapi.query_status(workflow_id=workflow_id)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        temporal = str(result.get("temporal_status") or "").upper()
        if any(x in temporal for x in ("COMPLETED", "FAILED", "TERMINATED", "CANCELED", "CANCELLED")):
            spt_guard.release_spt(workflow_id)
        return result

    @app.post("/v1/handoff")
    def do_handoff(
        body: HandoffBody,
        _: str = Depends(require_token),
    ) -> dict[str, str]:
        try:
            run_ref = handoff.handoff(
                from_run_ref=body.from_run_ref,
                to_kind=body.to_kind,
                depth=body.depth,
                context=body.context,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"run_ref": run_ref, "from_run_ref": body.from_run_ref}

    return app


app = create_app()


def main() -> None:
    import uvicorn

    host = os.getenv("GATEWAY_HOST", "0.0.0.0")
    port = int(os.getenv("GATEWAY_PORT", "8090"))
    uvicorn.run("agent_gateway.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
