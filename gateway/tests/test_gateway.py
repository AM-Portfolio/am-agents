"""Gateway auth + SPT concurrent guard (no Temporal)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GATEWAY_API_TOKEN", "test-token")
    monkeypatch.setenv("RUN_STORE_PROVIDER", "fake")
    monkeypatch.setenv("SPT_MAX_CONCURRENT_RUNS", "1")
    # fresh module state
    from agent_gateway import spt_guard

    spt_guard._active_spt.clear()
    from agent_gateway.app import create_app

    return TestClient(create_app())


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200


def test_auth_required(client: TestClient) -> None:
    r = client.post("/v1/workflows/alert-incident", json={"tracking_id": "t1", "alert": {}})
    assert r.status_code == 401


def test_auth_rejects_bad_token(client: TestClient) -> None:
    r = client.post(
        "/v1/workflows/alert-incident",
        json={"tracking_id": "t1", "alert": {}},
        headers={"Authorization": "Bearer wrong"},
    )
    assert r.status_code == 403


def test_handoff_via_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    from am_platform_ports.fakes import FakeRunStore
    from am_platform_ports.schemas.enums import RunKind
    from am_platform_ports.schemas.run import CreateRunRequest
    from am_platform_ports.fakes import FakeHandoff
    import agent_gateway.app as appmod

    monkeypatch.setenv("GATEWAY_API_TOKEN", "test-token")
    rs = FakeRunStore()
    parent = rs.create_run(CreateRunRequest(kind=RunKind.ALERT_INCIDENT, incident_ref="h1"))
    monkeypatch.setattr(appmod, "build_run_store", lambda: rs)
    monkeypatch.setattr(appmod, "build_handoff", lambda runs=None: FakeHandoff(rs))

    c = TestClient(appmod.create_app())
    ok = c.post(
        "/v1/handoff",
        json={"from_run_ref": parent.run_ref, "to_kind": "spt", "depth": 1},
        headers={"Authorization": "Bearer test-token"},
    )
    assert ok.status_code == 200, ok.text
    child = ok.json()["run_ref"]
    bad = c.post(
        "/v1/handoff",
        json={"from_run_ref": child, "to_kind": "verify", "depth": 2},
        headers={"Authorization": "Bearer test-token"},
    )
    assert bad.status_code == 403


def test_spt_guard_blocks_second(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPT_MAX_CONCURRENT_RUNS", "1")
    from agent_gateway import spt_guard

    spt_guard._active_spt.clear()
    spt_guard.try_acquire_spt("wf-1")
    with pytest.raises(PermissionError):
        spt_guard.try_acquire_spt("wf-2")
    spt_guard.release_spt("wf-1")
    spt_guard.try_acquire_spt("wf-2")
