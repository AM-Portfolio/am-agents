"""Router and plan runner tests."""

from __future__ import annotations

import httpx
import pytest

from am_support_agent.adapters import build_adapters
from am_support_agent.contracts.enums import A2AOp, TaskStatus
from am_support_agent.orchestrator import PlanRunner, PlannedTask, Planner
from am_support_agent.orchestrator.router import Router
from am_support_agent.registry import AgentRegistry, default_registry_path, load_registry_dict


def _reg() -> AgentRegistry:
    return AgentRegistry(load_registry_dict(default_registry_path()))


def test_router_prefers_tool():
    r = Router(_reg())
    assert r.route(capability="tools.execute").agent_id == "tool-agent"


def test_router_blocks_db_without_legacy():
    r = Router(_reg())
    with pytest.raises(PermissionError):
        r.route(agent_id="db-agent")


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/health"):
        return httpx.Response(200, json={"status": "ok"})
    if request.url.path.endswith("/api/v1/tools/execute"):
        return httpx.Response(200, json={"run_id": "r1", "ok": True})
    return httpx.Response(404, json={"error": "missing"})


@pytest.mark.asyncio
async def test_plan_runner_executes():
    reg = _reg()
    for c in reg.list_cards():
        c.base_url = "http://mock"
    adapters = build_adapters(
        reg.list_cards(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(_handler)),
    )
    runner = PlanRunner(reg, adapters)
    out = await runner.run(
        correlation_id="c-run",
        tasks=[
            PlannedTask(
                agent_id="",
                capability="tools.execute",
                op=A2AOp.EXECUTE,
                payload={"tool": "x"},
            )
        ],
    )
    assert out["status"] == TaskStatus.SUCCEEDED.value
    assert out["results"][0]["agent_id"] == "tool-agent"
