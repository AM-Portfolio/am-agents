"""Gateway v2 API tests."""

from __future__ import annotations

import httpx
import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from am_support_agent.adapters import build_adapters
from am_support_agent.contracts.enums import A2AOp
from am_support_agent.contracts.schemas import TaskRequest, TaskResult
from am_support_agent.gateway.app import A2ABody, _auth
from am_support_agent.identity import AGENT_ID
from am_support_agent.registry import get_registry
from am_support_agent.runtime import IdempotencyStore, new_task_id


def _mock_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/health"):
        return httpx.Response(200, json={"status": "ok"})
    if request.url.path.endswith("/api/v1/tools/execute"):
        return httpx.Response(200, json={"run_id": "x", "ok": True})
    return httpx.Response(404, json={"error": "missing"})


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_API_TOKEN", "test-token")
    get_registry.cache_clear()
    registry = get_registry()
    for c in registry.list_cards():
        c.base_url = "http://mock.agent"
    adapters = build_adapters(
        registry.list_cards(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(_mock_handler)),
    )
    idem = IdempotencyStore()
    application = FastAPI()

    @application.get("/healthz")
    def healthz():
        return {
            "status": "ok",
            "service": "support-agent-gateway",
            "agent_id": AGENT_ID,
            "generation": "v2",
        }

    @application.post("/v2/a2a", response_model=TaskResult)
    async def a2a(body: A2ABody, _: str = Depends(_auth)) -> TaskResult:
        if body.agent_id == "db-agent" and not body.require_legacy_db:
            raise HTTPException(status_code=403, detail="legacy required")
        agent_id = body.agent_id or registry.prefer
        adapter = adapters[agent_id]
        task_id = new_task_id()
        request = TaskRequest(
            task_id=task_id,
            agent_id=agent_id,
            capability=body.capability,
            op=body.op,
            idempotency_key=body.idempotency_key,
            budget=registry.default_budget,
            payload=body.payload,
        )
        if body.op == A2AOp.EXECUTE and body.idempotency_key:
            cached = idem.get(agent_id, body.idempotency_key)
            if cached is not None:
                return TaskResult.model_validate(cached)
        result = await adapter.handle(request)
        if body.op == A2AOp.EXECUTE and body.idempotency_key:
            idem.put(agent_id, body.idempotency_key, result.model_dump())
        return result

    with TestClient(application) as tc:
        yield tc
    get_registry.cache_clear()


def test_healthz_no_auth(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["agent_id"] == "support-agent"


def test_a2a_requires_auth(client):
    r = client.post("/v2/a2a", json={"op": "discover", "agent_id": "tool-agent"})
    assert r.status_code in (401, 403, 503)


def test_a2a_execute_idempotent(client):
    headers = {"Authorization": "Bearer test-token"}
    body = {
        "agent_id": "tool-agent",
        "op": "execute",
        "idempotency_key": "same-key",
        "payload": {"tool": "x"},
    }
    r1 = client.post("/v2/a2a", headers=headers, json=body)
    r2 = client.post("/v2/a2a", headers=headers, json=body)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["task_id"] == r2.json()["task_id"]


def test_db_blocked_without_legacy(client):
    headers = {"Authorization": "Bearer test-token"}
    r = client.post(
        "/v2/a2a",
        headers=headers,
        json={"agent_id": "db-agent", "op": "discover"},
    )
    assert r.status_code == 403
