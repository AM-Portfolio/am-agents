"""Adapter tests with httpx MockTransport — no live specialists required."""

from __future__ import annotations

import json

import httpx
import pytest

from am_support_agent.adapters import (
    DbAgentAdapter,
    ToolAgentAdapter,
    UiTestAgentAdapter,
    build_adapters,
)
from am_support_agent.contracts.enums import A2AOp, TaskStatus
from am_support_agent.contracts.schemas import TaskRequest
from am_support_agent.registry import AgentRegistry, default_registry_path, load_registry_dict


def _registry() -> AgentRegistry:
    return AgentRegistry(load_registry_dict(default_registry_path()))


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/health"):
        return httpx.Response(200, json={"status": "ok", "tools": ["grafana"]})
    if path.endswith("/api/v1/tools/plan"):
        return httpx.Response(200, json={"steps": [{"tool": "grafana.query"}]})
    if path.endswith("/api/v1/tools/execute"):
        return httpx.Response(200, json={"run_id": "tr-1", "ok": True})
    if path.endswith("/api/v1/db/plan"):
        return httpx.Response(200, json={"steps": [{"sql": "select 1"}]})
    if path.endswith("/api/v1/db/execute"):
        return httpx.Response(200, json={"rows": [[1]]})
    if path.endswith("/api/v1/test/run"):
        return httpx.Response(200, json={"testId": "ui-99"})
    if "/api/v1/test/status/" in path:
        return httpx.Response(200, json={"status": "completed", "testId": "ui-99"})
    return httpx.Response(404, json={"error": "not found", "path": path})


@pytest.fixture
def client():
    transport = httpx.MockTransport(_handler)
    return httpx.AsyncClient(transport=transport, base_url="http://agent.test")


@pytest.mark.asyncio
async def test_tool_discover_plan_execute(client):
    reg = _registry()
    card = reg.get("tool-agent")
    card.base_url = "http://agent.test"
    adapter = ToolAgentAdapter(card, client=client)

    disc = await adapter.handle(
        TaskRequest(task_id="1", agent_id="tool-agent", op=A2AOp.DISCOVER)
    )
    assert disc.status == TaskStatus.SUCCEEDED
    assert disc.data["agent_card"]["agent_id"] == "tool-agent"

    plan = await adapter.handle(
        TaskRequest(
            task_id="2",
            agent_id="tool-agent",
            op=A2AOp.PLAN,
            payload={"goal": "check grafana"},
        )
    )
    assert plan.status == TaskStatus.SUCCEEDED

    exe = await adapter.handle(
        TaskRequest(
            task_id="3",
            agent_id="tool-agent",
            op=A2AOp.EXECUTE,
            idempotency_key="k1",
            payload={"tool": "grafana.query"},
        )
    )
    assert exe.status == TaskStatus.SUCCEEDED
    assert exe.evidence[0].ref == "tr-1"

    missing = await adapter.handle(
        TaskRequest(task_id="4", agent_id="tool-agent", op=A2AOp.EXECUTE, payload={})
    )
    assert missing.status == TaskStatus.FAILED
    assert missing.error and missing.error.code == "idempotency_required"


@pytest.mark.asyncio
async def test_ui_synthesizes_plan_and_status(client):
    card = _registry().get("ui-test-agent")
    card.base_url = "http://agent.test"
    adapter = UiTestAgentAdapter(card, client=client)

    plan = await adapter.handle(
        TaskRequest(
            task_id="u1",
            agent_id="ui-test-agent",
            op=A2AOp.PLAN,
            payload={"suite": "smoke"},
        )
    )
    assert plan.data["synthesized"] is True

    exe = await adapter.handle(
        TaskRequest(
            task_id="u2",
            agent_id="ui-test-agent",
            op=A2AOp.EXECUTE,
            idempotency_key="ui-k",
            payload={"suite": "smoke"},
        )
    )
    assert exe.status == TaskStatus.RUNNING
    assert exe.evidence[0].ref == "ui-99"

    st = await adapter.handle(
        TaskRequest(task_id="u2", agent_id="ui-test-agent", op=A2AOp.STATUS)
    )
    assert st.status == TaskStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_cancel_and_feedback_are_platform_local(client):
    card = _registry().get("db-agent")
    card.base_url = "http://agent.test"
    adapter = DbAgentAdapter(card, client=client, caller_header_value="platform")

    cancel = await adapter.handle(
        TaskRequest(task_id="d1", agent_id="db-agent", op=A2AOp.CANCEL)
    )
    assert cancel.status == TaskStatus.CANCELLED

    fb = await adapter.handle(
        TaskRequest(
            task_id="d1",
            agent_id="db-agent",
            op=A2AOp.FEEDBACK,
            payload={"rating": "pass"},
        )
    )
    assert fb.status == TaskStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_build_adapters_covers_registry(client):
    reg = _registry()
    for c in reg.list_cards():
        c.base_url = "http://agent.test"
    adapters = build_adapters(reg.list_cards(), client=client)
    assert set(adapters) == {"tool-agent", "db-agent", "ui-test-agent"}
