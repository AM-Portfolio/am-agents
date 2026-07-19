"""Parallel Support Agent gateway v2 (distinct from legacy gateway/)."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Response, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from am_support_agent.adapters import BaseHttpAdapter, build_adapters
from am_support_agent.composition import SupportRuntime, build_runtime
from am_support_agent.contracts.enums import A2AOp, SupportDomain
from am_support_agent.contracts.schemas import TaskRequest, TaskResult
from am_support_agent.identity import agent_id as platform_agent_id
from am_support_agent.identity import display_name as platform_display_name
from am_support_agent.integrations import kagent_integration_status
from am_support_agent.learning import configure_learning, learning_status
from am_support_agent.orchestrator import PlanRunner, PlannedTask, Planner
from am_support_agent.orchestrator.execution import ExecutionService
from am_support_agent.orchestrator.hitl import HITL_SIGNAL_NAMES
from am_support_agent.orchestrator.router import Router
from am_support_agent.observability import Metrics, setup_tracing, temporal_interceptors
from am_support_agent.parity import (
    FeatureFlagProvider,
    SHADOW_MATCH_THRESHOLD,
    build_feature_flags,
    canary_config,
    compare_results,
    decide_route_runtime,
    require_support_route_runtime,
)
from am_support_agent.registry import AgentRegistry, get_registry
from am_support_agent.runtime import (
    merge_budget,
    new_task_id,
    require_gateway_token,
)
from am_support_agent.stores import TaskRunStore, build_task_run_store
from am_support_agent.stores.workflow_ledger import (
    WorkflowKind,
    WorkflowLedger,
    WorkflowRunStatus,
    WorkflowStepStatus,
    build_workflow_ledger,
)
from am_support_agent.orchestrator import temporal_api as tapi

_scheme = HTTPBearer(auto_error=False)


def _auth(
    creds: HTTPAuthorizationCredentials | None = Security(_scheme),
) -> str:
    try:
        token = creds.credentials if creds and creds.scheme.lower() == "bearer" else None
        require_gateway_token(token)
        return token or ""
    except PermissionError as exc:
        detail = str(exc)
        code = 503 if "not configured" in detail else 401 if not creds else 403
        raise HTTPException(status_code=code, detail=detail) from exc


class A2ABody(BaseModel):
    agent_id: str | None = None
    capability: str = ""
    op: A2AOp
    business_domain: SupportDomain = SupportDomain.UNKNOWN
    requires_human: bool = False
    correlation_id: str = ""
    idempotency_key: str | None = None
    require_legacy_db: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)
    max_latency_ms: int | None = None
    max_cost_units: float | None = None
    max_fanout: int | None = None


class PlannedTaskBody(BaseModel):
    agent_id: str = ""
    capability: str = ""
    op: A2AOp = A2AOp.EXECUTE
    business_domain: SupportDomain = SupportDomain.UNKNOWN
    requires_human: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)
    require_legacy_db: bool = False


class RunPlanBody(BaseModel):
    correlation_id: str = ""
    tasks: list[PlannedTaskBody]


class ShadowBody(BaseModel):
    task: A2ABody
    legacy_result: dict[str, Any]


class AlertIncidentStartBody(BaseModel):
    tracking_id: str
    alert: dict[str, Any] = Field(default_factory=dict)
    run_ref: str | None = None


class SptStartBody(BaseModel):
    demand: dict[str, Any] = Field(default_factory=dict)
    workflow_id: str | None = None
    run_ref: str | None = None


class HandoffBody(BaseModel):
    from_run_ref: str
    to_kind: str = WorkflowKind.HANDOFF.value
    depth: int = 1
    context: dict[str, Any] = Field(default_factory=dict)


class CanaryDecideBody(BaseModel):
    key: str = ""


class WorkflowFeedbackBody(BaseModel):
    kind: str = "silence"
    requester: str = ""
    reason: str = ""
    notes: str = ""
    duration_minutes: int = 60
    env: str = ""
    service: str = ""
    request_id: str = ""
    matchers: dict[str, str] = Field(default_factory=dict)


class WorkflowApprovalBody(BaseModel):
    request_id: str = ""
    actor: str = ""
    scope_hash: str = ""
    notes: str = ""
    timestamp: str = ""


def create_app(
    *,
    registry: AgentRegistry | None = None,
    adapters: dict[str, BaseHttpAdapter] | None = None,
    store: TaskRunStore | None = None,
    workflow_ledger: WorkflowLedger | None = None,
    metrics: Metrics | None = None,
    runtime: SupportRuntime | None = None,
    feature_flags: FeatureFlagProvider | None = None,
) -> FastAPI:
    feature_flags = feature_flags or build_feature_flags()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        await feature_flags.close()

    app = FastAPI(
        title="Support Agent Gateway (v2)",
        version="0.1.0",
        description=(
            "Parallel A2A gateway for support-agent. Does not replace legacy "
            "agent-gateway until production gates pass."
        ),
        lifespan=lifespan,
    )
    registry = registry or get_registry()
    adapters = adapters or build_adapters(registry.list_cards())
    store = store or build_task_run_store()
    workflow_ledger = workflow_ledger or build_workflow_ledger()
    if metrics is None:
        from am_support_agent.observability.metrics import get_shared_metrics

        metrics = get_shared_metrics()
    else:
        from am_support_agent.observability.metrics import set_shared_metrics

        set_shared_metrics(metrics)
    runtime = runtime or build_runtime(workflow_ledger=workflow_ledger)
    configure_learning(
        episodes=runtime.episodes,
        feedback=runtime.feedback,
        metrics=metrics,
    )
    metrics.set_episode_store_health(runtime.episodes.ready())
    metrics.set_feedback_store_health(runtime.feedback.ready())
    router = Router(registry)
    planner = Planner(registry)
    execution = ExecutionService(adapters, store, metrics)
    runner = PlanRunner(registry, adapters, execution)
    app.state.registry = registry
    app.state.adapters = adapters
    app.state.store = store
    app.state.workflow_ledger = runtime.workflow_ledger
    app.state.runtime = runtime
    app.state.feature_flags = feature_flags
    app.state.metrics = metrics
    app.state.execution = execution
    setup_tracing(app)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "support-agent-gateway",
            "agent_id": platform_agent_id(),
            "display_name": platform_display_name(),
            "generation": "v2",
        }

    @app.get("/readyz")
    def readyz() -> dict[str, Any]:
        if not execution.ready():
            raise HTTPException(status_code=503, detail="run store unavailable")
        readiness = runtime.readiness()
        if not readiness["ready"]:
            raise HTTPException(
                status_code=503,
                detail={
                    "message": "required adapters not ready",
                    "missing": readiness["missing"],
                },
            )
        return {
            "status": "ready",
            "run_store": "ready",
            "runtime_mode": readiness["mode"],
            "memory": {
                "episodes": readiness["components"]["episodes"],
                "feedback": readiness["components"]["feedback"],
                "workflow_ledger": readiness["components"]["workflow_ledger"],
            },
            "adapters": {
                name: bool(info.get("wired"))
                for name, info in readiness["components"].items()
            },
        }

    @app.get("/metrics")
    def prometheus_metrics() -> Response:
        return Response(
            content=metrics.render(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @app.get("/v2/agents")
    def list_agents(_: str = Depends(_auth)) -> dict[str, Any]:
        return {
            "platform": {
                "agent_id": registry.platform_agent_id,
                "display_name": registry.platform_display_name,
            },
            "prefer": registry.prefer,
            "agents": [c.model_dump() for c in registry.list_cards()],
        }

    @app.get("/v2/catalog")
    def catalog_summary(_: str = Depends(_auth)) -> dict[str, Any]:
        """Read-only procedural memory summary from monorepo catalog/."""
        return runtime.catalog.summary()

    @app.get("/v2/integrations")
    def integrations(_: str = Depends(_auth)) -> dict[str, Any]:
        readiness = runtime.readiness()
        return {
            "kagent": kagent_integration_status(),
            "runtime": readiness,
            "llm": readiness["components"]["llm"],
            "docstore": readiness["components"]["documents"],
            "capability": readiness["components"]["capability"],
            "prompts": readiness["components"]["prompts"],
            "catalog": readiness["components"]["catalog"],
            "semantic": readiness["components"]["semantic"],
            "episodes": readiness["components"]["episodes"],
            "feedback": readiness["components"]["feedback"],
            "workflow_ledger": readiness["components"]["workflow_ledger"],
            "learning": learning_status(),
            "hitl_signals": sorted(HITL_SIGNAL_NAMES),
            "canary": {
                **canary_config(),
                "feature_flags": feature_flags.status(),
            },
        }

    @app.get("/v2/canary")
    def canary_status(_: str = Depends(_auth)) -> dict[str, Any]:
        """Canary config + rollback hint (legacy remains default)."""
        return {
            **canary_config(),
            "feature_flags": feature_flags.status(),
        }

    @app.post("/v2/canary/decide")
    async def canary_decide(
        body: CanaryDecideBody, _: str = Depends(_auth)
    ) -> dict[str, Any]:
        decision = await decide_route_runtime(
            body.key,
            feature_flags=feature_flags,
        )
        metrics.observe_canary(mode=decision.mode.value, route=decision.route.value)
        return decision.as_dict()

    @app.post("/v2/a2a", response_model=TaskResult)
    async def a2a(body: A2ABody, _: str = Depends(_auth)) -> TaskResult:
        try:
            agent_id = router.route(
                agent_id=body.agent_id,
                capability=body.capability,
                require_legacy_db=body.require_legacy_db,
            ).agent_id
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        task_id = new_task_id()
        budget_updates = {
            k: v
            for k, v in {
                "max_latency_ms": body.max_latency_ms,
                "max_cost_units": body.max_cost_units,
                "max_fanout": body.max_fanout,
            }.items()
            if v is not None
        }
        request_budget = registry.default_budget.model_copy(update=budget_updates)
        request = TaskRequest(
            task_id=task_id,
            correlation_id=body.correlation_id,
            agent_id=agent_id,
            capability=body.capability,
            op=body.op,
            business_domain=body.business_domain,
            requires_human=body.requires_human,
            idempotency_key=body.idempotency_key,
            budget=merge_budget(
                TaskRequest(
                    task_id=task_id,
                    agent_id=agent_id,
                    op=body.op,
                    budget=request_budget,
                ),
                registry.default_budget,
            ),
            payload=body.payload,
        )

        return await execution.execute(request)

    @app.get("/v2/tasks/{task_id}")
    def task_status(task_id: str, _: str = Depends(_auth)) -> dict[str, Any]:
        run = execution.status(task_id)
        if run is None:
            raise HTTPException(status_code=404, detail="unknown task")
        return run

    @app.post("/v2/shadow")
    async def shadow_compare(
        body: ShadowBody, _: str = Depends(_auth)
    ) -> dict[str, Any]:
        """Compare side-effect-free replacement output with a legacy result."""
        if body.task.op not in {A2AOp.DISCOVER, A2AOp.PLAN}:
            raise HTTPException(
                status_code=400,
                detail="shadow endpoint allows discover/plan only; execute is forbidden",
            )
        try:
            agent_id = router.route(
                agent_id=body.task.agent_id,
                capability=body.task.capability,
                require_legacy_db=body.task.require_legacy_db,
            ).agent_id
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        request = TaskRequest(
            task_id=new_task_id(),
            correlation_id=body.task.correlation_id,
            agent_id=agent_id,
            capability=body.task.capability,
            op=body.task.op,
            business_domain=body.task.business_domain,
            requires_human=body.task.requires_human,
            payload=body.task.payload,
        )
        replacement = await execution.execute(request)
        report = compare_results(
            body.legacy_result,
            replacement.model_dump(mode="json"),
            threshold=SHADOW_MATCH_THRESHOLD,
        )
        metrics.observe_parity(body.task.business_domain, report.matched)
        return {
            "mode": "shadow_no_side_effects",
            "threshold": SHADOW_MATCH_THRESHOLD,
            "replacement": replacement.model_dump(mode="json"),
            "parity": report.model_dump(mode="json"),
        }

    @app.post("/v2/plan")
    def plan_only(body: RunPlanBody, _: str = Depends(_auth)) -> dict[str, Any]:
        try:
            plan = planner.plan(
                correlation_id=body.correlation_id or new_task_id(),
                tasks=[
                    PlannedTask(
                        agent_id=t.agent_id,
                        capability=t.capability,
                        op=t.op,
                        business_domain=t.business_domain,
                        requires_human=t.requires_human,
                        payload=t.payload,
                        require_legacy_db=t.require_legacy_db,
                    )
                    for t in body.tasks
                ],
            )
        except (PermissionError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "correlation_id": plan.correlation_id,
            "budget": plan.budget.model_dump(),
            "tasks": [
                {
                    "agent_id": t.agent_id,
                    "capability": t.capability,
                    "op": t.op.value,
                }
                for t in plan.tasks
            ],
        }

    @app.post("/v2/run")
    async def run_plan(body: RunPlanBody, _: str = Depends(_auth)) -> dict[str, Any]:
        try:
            return await runner.run(
                correlation_id=body.correlation_id or new_task_id(),
                tasks=[
                    PlannedTask(
                        agent_id=t.agent_id,
                        capability=t.capability,
                        op=t.op,
                        business_domain=t.business_domain,
                        requires_human=t.requires_human,
                        payload=t.payload,
                        require_legacy_db=t.require_legacy_db,
                    )
                    for t in body.tasks
                ],
            )
        except (PermissionError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/v2/workflows/a2a")
    async def start_a2a_workflow(
        body: RunPlanBody, _: str = Depends(_auth)
    ) -> dict[str, Any]:
        """Start SupportA2AWorkflow on queue support-agent-v2 (optional Temporal)."""
        if os.getenv("SUPPORT_AGENT_TEMPORAL_ENABLED", "").lower() not in {
            "1",
            "true",
            "yes",
        }:
            raise HTTPException(
                status_code=503,
                detail="Temporal disabled; set SUPPORT_AGENT_TEMPORAL_ENABLED=true",
            )
        try:
            from temporalio.client import Client
        except ImportError as exc:
            raise HTTPException(
                status_code=503,
                detail="temporalio not installed (pip install am-support-agent[temporal])",
            ) from exc

        host = os.getenv("TEMPORAL_HOST", "localhost:7233")
        ns = os.getenv("TEMPORAL_NAMESPACE", "default")
        queue = os.getenv("TEMPORAL_TASK_QUEUE", "support-agent-v2")
        if queue == "agent-platform":
            raise HTTPException(
                status_code=400,
                detail="Refusing legacy Temporal queue agent-platform",
            )
        correlation_id = body.correlation_id or new_task_id()
        payload = {
            "correlation_id": correlation_id,
            "tasks": [t.model_dump(mode="json") for t in body.tasks],
        }
        client = await Client.connect(
            host,
            namespace=ns,
            interceptors=temporal_interceptors(),
        )
        handle = await client.start_workflow(
            "SupportA2AWorkflow",
            payload,
            id=f"support-a2a-{correlation_id}",
            task_queue=queue,
        )
        return {
            "workflow_id": handle.id,
            "run_id": handle.result_run_id,
            "task_queue": queue,
            "correlation_id": correlation_id,
        }

    @app.post("/v2/workflows/alert-incident")
    async def start_alert_incident(
        body: AlertIncidentStartBody, _: str = Depends(_auth)
    ) -> dict[str, Any]:
        tracking_id = body.tracking_id.strip()
        if not tracking_id:
            raise HTTPException(status_code=400, detail="tracking_id required")
        try:
            decision = await require_support_route_runtime(
                tracking_id,
                feature_flags=feature_flags,
                attributes={
                    "workflow": "alert-incident",
                    "service": str(body.alert.get("service") or "support-agent"),
                },
            )
        except ValueError as exc:
            denied = await decide_route_runtime(
                tracking_id,
                feature_flags=feature_flags,
                attributes={
                    "workflow": "alert-incident",
                    "service": str(body.alert.get("service") or "support-agent"),
                },
            )
            metrics.observe_canary(mode=denied.mode.value, route=denied.route.value)
            raise HTTPException(
                status_code=409,
                detail={"error": str(exc), "canary": denied.as_dict()},
            ) from exc
        metrics.observe_canary(mode=decision.mode.value, route=decision.route.value)
        if not tapi.temporal_enabled():
            raise HTTPException(
                status_code=503,
                detail="Temporal disabled; set SUPPORT_AGENT_TEMPORAL_ENABLED=true",
            )
        workflow_id = f"alert-incident-{tracking_id}"
        run = workflow_ledger.create_run(
            kind=WorkflowKind.ALERT_INCIDENT,
            tracking_id=tracking_id,
            workflow_id=workflow_id,
            run_ref=body.run_ref,
            summary={"alert_keys": sorted((body.alert or {}).keys())},
        )
        try:
            from am_support_agent.observability.agent_work import build_event
            from am_support_agent.stores.telemetry_outbox import build_telemetry_outbox

            build_telemetry_outbox().append(
                build_event(
                    event_name="agent.work.accepted",
                    status="accepted",
                    outcome="unknown",
                    workflow_id=workflow_id,
                    run_ref=run.run_ref,
                    tracking_id=tracking_id,
                    sequence=0,
                    environment=str(
                        (body.alert or {}).get("env")
                        or (body.alert or {}).get("environment")
                        or ""
                    ),
                )
            )
            metrics.observe_agent_work(
                work_kind="alert_incident",
                status="accepted",
                outcome="unknown",
                event_name="agent.work.accepted",
            )
        except Exception:  # noqa: BLE001
            pass
        try:
            result = await tapi.start_alert_incident(
                workflow_id=workflow_id,
                tracking_id=tracking_id,
                alert=body.alert or {},
                run_ref=run.run_ref,
            )
        except Exception as exc:  # noqa: BLE001
            workflow_ledger.update_run(
                run.run_ref,
                status=WorkflowRunStatus.FAILED,
                summary={"error": str(exc)[:200]},
            )
            # Phase 2 stub: if Temporal rejects duplicate on a terminal workflow,
            # surface dropped_refire so ops can see received ≠ processed.
            detail = str(exc)[:400]
            if "already" in detail.lower() or "duplicate" in detail.lower():
                try:
                    metrics.observe_agent_work(
                        work_kind="alert_incident",
                        status="failed",
                        outcome="failed",
                        event_name="incident.refired",
                    )
                except Exception:  # noqa: BLE001
                    pass
            raise HTTPException(status_code=502, detail=detail) from exc
        workflow_ledger.update_run(
            run.run_ref,
            status=WorkflowRunStatus.RUNNING,
            workflow_id=workflow_id,
            summary={"temporal_action": result.get("action")},
        )
        return {**result, "module": "support-agent"}

    @app.post("/v2/workflows/spt")
    async def start_spt(
        body: SptStartBody, _: str = Depends(_auth)
    ) -> dict[str, Any]:
        demand = dict(body.demand or {})
        demand_ref = str(demand.get("demand_ref") or "").strip()
        if not demand_ref:
            raise HTTPException(status_code=400, detail="demand.demand_ref required")
        try:
            decision = await require_support_route_runtime(
                demand_ref,
                feature_flags=feature_flags,
                attributes={"workflow": "spt"},
            )
        except ValueError as exc:
            denied = await decide_route_runtime(
                demand_ref,
                feature_flags=feature_flags,
                attributes={"workflow": "spt"},
            )
            metrics.observe_canary(mode=denied.mode.value, route=denied.route.value)
            raise HTTPException(
                status_code=409,
                detail={"error": str(exc), "canary": denied.as_dict()},
            ) from exc
        metrics.observe_canary(mode=decision.mode.value, route=decision.route.value)
        if not tapi.temporal_enabled():
            raise HTTPException(
                status_code=503,
                detail="Temporal disabled; set SUPPORT_AGENT_TEMPORAL_ENABLED=true",
            )
        workflow_id = body.workflow_id or f"spt-{demand_ref}-{new_task_id()[:8]}"
        run = workflow_ledger.create_run(
            kind=WorkflowKind.SPT,
            tracking_id=demand_ref,
            workflow_id=workflow_id,
            demand_ref=demand_ref,
            run_ref=body.run_ref,
            summary={"demand_keys": sorted(demand.keys())},
        )
        try:
            result = await tapi.start_spt(
                workflow_id=workflow_id,
                demand=demand,
                run_ref=run.run_ref,
            )
        except Exception as exc:  # noqa: BLE001
            workflow_ledger.update_run(
                run.run_ref,
                status=WorkflowRunStatus.FAILED,
                summary={"error": str(exc)[:200]},
            )
            raise HTTPException(status_code=502, detail=str(exc)[:400]) from exc
        workflow_ledger.update_run(
            run.run_ref,
            status=WorkflowRunStatus.RUNNING,
            workflow_id=workflow_id,
            summary={"temporal_action": result.get("action")},
        )
        return {**result, "module": "support-agent"}

    @app.post("/v2/workflows/{workflow_id}/signals/{signal_name}")
    async def signal_workflow(
        workflow_id: str,
        signal_name: str,
        body: dict[str, Any] | None = None,
        _: str = Depends(_auth),
    ) -> dict[str, Any]:
        if signal_name not in HITL_SIGNAL_NAMES:
            raise HTTPException(
                status_code=400, detail=f"signal not allowed: {signal_name}"
            )
        if not tapi.temporal_enabled():
            raise HTTPException(
                status_code=503,
                detail="Temporal disabled; set SUPPORT_AGENT_TEMPORAL_ENABLED=true",
            )
        try:
            result = await tapi.signal_workflow(
                workflow_id=workflow_id,
                signal_name=signal_name,
                payload=dict(body or {}) or None,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)[:400]) from exc
        ledger_run = workflow_ledger.get_by_workflow_id(workflow_id)
        if ledger_run is not None:
            workflow_ledger.upsert_step(
                run_ref=ledger_run.run_ref,
                name=f"signal.{signal_name}",
                status=WorkflowStepStatus.PASSED,
                bump_attempts=True,
                detail={"signal": signal_name, "payload_keys": sorted((body or {}).keys())},
            )
        return {**result, "module": "support-agent"}

    @app.post("/v2/workflows/{workflow_id}/feedback")
    async def workflow_feedback(
        workflow_id: str,
        body: WorkflowFeedbackBody,
        _: str = Depends(_auth),
    ) -> dict[str, Any]:
        """Canonical authenticated feedback intake (silence / disable candidate / note)."""
        if not tapi.temporal_enabled():
            raise HTTPException(
                status_code=503,
                detail="Temporal disabled; set SUPPORT_AGENT_TEMPORAL_ENABLED=true",
            )
        payload = body.model_dump()
        payload["workflow_id"] = workflow_id
        try:
            result = await tapi.signal_workflow(
                workflow_id=workflow_id,
                signal_name="alert.feedback",
                payload=payload,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)[:400]) from exc
        ledger_run = workflow_ledger.get_by_workflow_id(workflow_id)
        if ledger_run is not None:
            workflow_ledger.upsert_step(
                run_ref=ledger_run.run_ref,
                name="signal.alert.feedback",
                status=WorkflowStepStatus.PASSED,
                bump_attempts=True,
                detail={"kind": body.kind, "requester": body.requester},
            )
        return {**result, "feedback": payload, "module": "support-agent"}

    @app.post("/v2/workflows/{workflow_id}/approvals/{purpose}")
    async def workflow_approval(
        workflow_id: str,
        purpose: str,
        body: WorkflowApprovalBody,
        _: str = Depends(_auth),
    ) -> dict[str, Any]:
        """Purpose-specific approval: investigation | known_fix | silence."""
        from am_support_agent.orchestrator.hitl import APPROVAL_PURPOSES

        if purpose not in APPROVAL_PURPOSES:
            raise HTTPException(
                status_code=400,
                detail=f"approval purpose not allowed: {purpose}",
            )
        signal_name = f"approve.{purpose}"
        if signal_name not in HITL_SIGNAL_NAMES:
            raise HTTPException(
                status_code=400, detail=f"signal not allowed: {signal_name}"
            )
        if not tapi.temporal_enabled():
            raise HTTPException(
                status_code=503,
                detail="Temporal disabled; set SUPPORT_AGENT_TEMPORAL_ENABLED=true",
            )
        payload = {
            "purpose": purpose,
            **body.model_dump(),
        }
        try:
            result = await tapi.signal_workflow(
                workflow_id=workflow_id,
                signal_name=signal_name,
                payload=payload,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)[:400]) from exc
        ledger_run = workflow_ledger.get_by_workflow_id(workflow_id)
        if ledger_run is not None:
            workflow_ledger.upsert_step(
                run_ref=ledger_run.run_ref,
                name=f"signal.{signal_name}",
                status=WorkflowStepStatus.PASSED,
                bump_attempts=True,
                detail=payload,
            )
        return {**result, "approval": payload, "module": "support-agent"}

    @app.get("/v2/workflows/{workflow_id}/status")
    async def workflow_status(
        workflow_id: str, _: str = Depends(_auth)
    ) -> dict[str, Any]:
        ledger_run = workflow_ledger.get_by_workflow_id(workflow_id)
        ledger_payload = (
            {
                "run_ref": ledger_run.run_ref,
                "kind": ledger_run.kind.value,
                "status": ledger_run.status.value,
                "tracking_id": ledger_run.tracking_id,
                "parent_run_ref": ledger_run.parent_run_ref,
                "summary": ledger_run.summary,
                "evidence_refs": ledger_run.evidence_refs,
                "validation": ledger_run.validation_json,
                "steps": [
                    s.model_dump(mode="json")
                    for s in workflow_ledger.list_steps(ledger_run.run_ref)
                ],
            }
            if ledger_run
            else None
        )
        if not tapi.temporal_enabled():
            if ledger_payload is None:
                raise HTTPException(status_code=404, detail="unknown workflow_id")
            return {
                "workflow_id": workflow_id,
                "temporal_status": "TEMPORAL_DISABLED",
                "ledger": ledger_payload,
                "module": "support-agent",
            }
        try:
            temporal = await tapi.query_status(workflow_id=workflow_id)
        except Exception as exc:  # noqa: BLE001
            if ledger_payload is None:
                raise HTTPException(status_code=502, detail=str(exc)[:400]) from exc
            return {
                "workflow_id": workflow_id,
                "temporal_error": str(exc)[:200],
                "ledger": ledger_payload,
                "module": "support-agent",
            }
        return {**temporal, "ledger": ledger_payload, "module": "support-agent"}

    @app.post("/v2/handoff")
    def handoff(body: HandoffBody, _: str = Depends(_auth)) -> dict[str, Any]:
        try:
            child = workflow_ledger.handoff(
                from_run_ref=body.from_run_ref,
                to_kind=body.to_kind,
                depth=body.depth,
                context=body.context,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "run_ref": child.run_ref,
            "from_run_ref": body.from_run_ref,
            "kind": child.kind.value,
            "module": "support-agent",
        }

    return app


def main() -> None:
    import uvicorn

    port = int(
        os.getenv("SUPPORT_AGENT_GATEWAY_PORT")
        or os.getenv("AGENT_PLATFORM_GATEWAY_PORT")
        or "8091"
    )
    uvicorn.run(
        "am_support_agent.gateway.app:create_app",
        factory=True,
        host=os.getenv(
            "SUPPORT_AGENT_GATEWAY_HOST",
            os.getenv("AGENT_PLATFORM_GATEWAY_HOST", "0.0.0.0"),
        ),
        port=port,
    )


app = create_app()
