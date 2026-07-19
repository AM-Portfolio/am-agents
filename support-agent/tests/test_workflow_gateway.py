"""Gateway workflow intake endpoints (ledger + Temporal gates)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from am_support_agent.gateway.app import create_app
from am_support_agent.observability import Metrics
from am_support_agent.registry import (
    AgentRegistry,
    default_registry_path,
    load_registry_dict,
)
from am_support_agent.stores import MemoryTaskRunStore, MemoryWorkflowLedger
from am_support_agent.stores.workflow_ledger import WorkflowKind


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_API_TOKEN", "test-token")
    monkeypatch.delenv("SUPPORT_AGENT_TEMPORAL_ENABLED", raising=False)
    app = create_app(
        registry=AgentRegistry(load_registry_dict(default_registry_path())),
        store=MemoryTaskRunStore(),
        workflow_ledger=MemoryWorkflowLedger(),
        metrics=Metrics(),
    )
    with TestClient(app) as test_client:
        yield test_client


def test_alert_incident_requires_temporal(client):
    headers = {"Authorization": "Bearer test-token"}
    resp = client.post(
        "/v2/workflows/alert-incident",
        headers=headers,
        json={"tracking_id": "trk-1", "alert": {"summary": "x"}},
    )
    assert resp.status_code == 503


def test_handoff_and_status_without_temporal(client):
    headers = {"Authorization": "Bearer test-token"}
    app = client.app
    ledger = app.state.workflow_ledger
    parent = ledger.create_run(
        kind=WorkflowKind.ALERT_INCIDENT,
        tracking_id="trk-2",
        workflow_id="alert-incident-trk-2",
    )
    handoff = client.post(
        "/v2/handoff",
        headers=headers,
        json={
            "from_run_ref": parent.run_ref,
            "to_kind": "handoff",
            "context": {"agent": "kagent_infra"},
        },
    )
    assert handoff.status_code == 200
    assert handoff.json()["from_run_ref"] == parent.run_ref

    status = client.get(
        "/v2/workflows/alert-incident-trk-2/status",
        headers=headers,
    )
    assert status.status_code == 200
    body = status.json()
    assert body["temporal_status"] == "TEMPORAL_DISABLED"
    assert body["ledger"]["run_ref"] == parent.run_ref
    assert body["ledger"]["steps"]


def test_signal_not_allowed(client):
    headers = {"Authorization": "Bearer test-token"}
    resp = client.post(
        "/v2/workflows/wf-1/signals/not-a-signal",
        headers=headers,
    )
    assert resp.status_code == 400


def test_alert_incident_starts_when_temporal_enabled(monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_API_TOKEN", "test-token")
    monkeypatch.setenv("SUPPORT_AGENT_TEMPORAL_ENABLED", "true")

    async def _start(**kwargs):
        return {
            "action": "started",
            "workflow_id": kwargs["workflow_id"],
            "run_ref": kwargs["run_ref"],
            "task_queue": "support-agent-v2",
        }

    monkeypatch.setattr(
        "am_support_agent.orchestrator.temporal_api.start_alert_incident",
        AsyncMock(side_effect=_start),
    )
    monkeypatch.setattr(
        "am_support_agent.orchestrator.temporal_api.temporal_enabled",
        lambda: True,
    )

    app = create_app(
        store=MemoryTaskRunStore(),
        workflow_ledger=MemoryWorkflowLedger(),
        metrics=Metrics(),
    )
    with TestClient(app) as client:
        resp = client.post(
            "/v2/workflows/alert-incident",
            headers={"Authorization": "Bearer test-token"},
            json={"tracking_id": "trk-9", "alert": {"summary": "disk"}},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "started"
    assert body["workflow_id"] == "alert-incident-trk-9"
    assert body["module"] == "support-agent"
