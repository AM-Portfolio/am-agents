"""Real gateway factory tests with injected specialist transports."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from am_support_agent.adapters import build_adapters
from am_support_agent.gateway.app import create_app
from am_support_agent.observability import Metrics
from am_support_agent.parity import FeatureFlagEvaluation
from am_support_agent.registry import (
    AgentRegistry,
    default_registry_path,
    load_registry_dict,
)
from am_support_agent.stores import MemoryTaskRunStore


class _FakeGrowthBook:
    def status(self):
        return {"enabled": True, "ready": True, "name": "growthbook"}

    async def evaluate(self, feature_key, *, fallback, attributes):
        return FeatureFlagEvaluation(
            feature_key=feature_key,
            value="new",
            source="growthbook",
            ready=True,
        )

    async def close(self):
        return None


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/health"):
        return httpx.Response(200, json={"status": "ok"})
    if request.url.path.endswith("/api/v1/tools/execute"):
        return httpx.Response(200, json={"run_id": "gateway-run", "ok": True})
    if request.url.path.endswith("/api/v1/tools/plan"):
        return httpx.Response(200, json={"steps": ["inspect", "verify"]})
    return httpx.Response(404, json={"error": "not_found"})


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_API_TOKEN", "test-token")
    registry = AgentRegistry(load_registry_dict(default_registry_path()))
    for card in registry.list_cards():
        card.base_url = "http://mock"
    adapters = build_adapters(
        registry.list_cards(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(_handler)),
    )
    app = create_app(
        registry=registry,
        adapters=adapters,
        store=MemoryTaskRunStore(),
        metrics=Metrics(),
        feature_flags=_FakeGrowthBook(),
    )
    with TestClient(app) as test_client:
        yield test_client


def test_health_readiness_and_metrics(client):
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").json()["status"] == "ready"
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "support_agent_a2a_requests_total" in metrics.text


def test_growthbook_canary_decision(client):
    headers = {"Authorization": "Bearer test-token"}
    response = client.post(
        "/v2/canary/decide",
        headers=headers,
        json={"key": "trk-growthbook"},
    )
    assert response.status_code == 200
    assert response.json()["route"] == "support"
    assert response.json()["source"] == "growthbook"


def test_durable_idempotency_and_task_status(client):
    headers = {"Authorization": "Bearer test-token"}
    body = {
        "agent_id": "tool-agent",
        "capability": "tools.execute",
        "op": "execute",
        "idempotency_key": "gateway-idem",
        "payload": {"tool": "x"},
    }
    first = client.post("/v2/a2a", headers=headers, json=body)
    second = client.post("/v2/a2a", headers=headers, json=body)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["task_id"] == second.json()["task_id"]

    status = client.get(
        f"/v2/tasks/{first.json()['task_id']}",
        headers=headers,
    )
    assert status.status_code == 200
    assert status.json()["status"] == "succeeded"

    metrics = client.get("/metrics").text
    assert 'agent="tool-agent"' in metrics
    assert 'status="succeeded"' in metrics


def test_unknown_task_and_db_gate(client):
    headers = {"Authorization": "Bearer test-token"}
    assert client.get("/v2/tasks/missing", headers=headers).status_code == 404
    denied = client.post(
        "/v2/a2a",
        headers=headers,
        json={"agent_id": "db-agent", "op": "discover"},
    )
    assert denied.status_code == 403


def test_shadow_is_side_effect_free_and_reports_parity(client):
    headers = {"Authorization": "Bearer test-token"}
    response = client.post(
        "/v2/shadow",
        headers=headers,
        json={
            "task": {
                "agent_id": "tool-agent",
                "capability": "tools.plan",
                "op": "plan",
                "payload": {"goal": "inspect"},
            },
            "legacy_result": {
                "status": "succeeded",
                "agent_id": "tool-agent",
                "evidence": [],
                "error": None,
                "metrics": {"cost_units": 0.0},
                "data": {"steps": ["inspect", "verify"]},
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["parity"]["matched"] is True
    assert response.json()["threshold"] == 1.0

    forbidden = client.post(
        "/v2/shadow",
        headers=headers,
        json={
            "task": {
                "agent_id": "tool-agent",
                "op": "execute",
                "idempotency_key": "shadow-write",
                "payload": {},
            },
            "legacy_result": {},
        },
    )
    assert forbidden.status_code == 400


def test_cancel_and_feedback_missing_target(client):
    headers = {"Authorization": "Bearer test-token"}
    cancel = client.post(
        "/v2/a2a",
        headers=headers,
        json={
            "agent_id": "tool-agent",
            "op": "cancel",
            "payload": {"target_task_id": "ghost-task"},
        },
    )
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"

    status = client.get("/v2/tasks/ghost-task", headers=headers)
    assert status.status_code == 200
    assert status.json()["status"] == "cancelled"

    fb = client.post(
        "/v2/a2a",
        headers=headers,
        json={
            "agent_id": "tool-agent",
            "op": "feedback",
            "payload": {"target_task_id": "ghost-task", "rating": "pass"},
        },
    )
    assert fb.status_code == 200
    recorded = client.get("/v2/tasks/ghost-task", headers=headers)
    assert len(recorded.json()["feedback"]) == 1


def test_catalog_and_integrations_endpoints(client, tmp_path, monkeypatch):
    catalog = tmp_path / "catalog"
    (catalog / "prompts").mkdir(parents=True)
    (catalog / "verify").mkdir()
    (catalog / "spt").mkdir()
    monkeypatch.setenv("SUPPORT_AGENT_CATALOG_ROOT", str(catalog))
    headers = {"Authorization": "Bearer test-token"}
    cat = client.get("/v2/catalog", headers=headers)
    assert cat.status_code == 200
    assert cat.json()["available"] is True
    integ = client.get("/v2/integrations", headers=headers)
    assert integ.status_code == 200
    body = integ.json()
    assert "approve" in body["hitl_signals"]
    assert body["kagent"]["executor"] == "tool-agent"
    assert body["learning"]["auto_promote"] is False
