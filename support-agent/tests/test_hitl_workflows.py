"""HITL signal continuity and gated incident/SPT activities."""

from __future__ import annotations

import pytest

from am_support_agent.orchestrator.hitl import (
    HITL_SIGNAL_NAMES,
    SIGNAL_ALERT_REFIRED,
    SIGNAL_ALERT_RESOLVED,
    SIGNAL_APPROVE,
    HitlState,
)


def test_hitl_signal_names_match_legacy():
    assert SIGNAL_APPROVE == "approve"
    assert SIGNAL_ALERT_RESOLVED == "alert.resolved"
    assert SIGNAL_ALERT_REFIRED == "alert.refired"
    assert HITL_SIGNAL_NAMES == {
        "approve",
        "alert.resolved",
        "alert.refired",
    }


def test_hitl_state_waiting():
    state = HitlState()
    assert not state.waiting_satisfied()
    state.apply_signal(SIGNAL_APPROVE)
    assert state.waiting_satisfied()
    assert state.as_dict()["approved"] is True


@pytest.mark.asyncio
async def test_incident_bootstrap_gated(monkeypatch):
    monkeypatch.delenv("SUPPORT_AGENT_INCIDENT_PARITY", raising=False)
    from am_support_agent.orchestrator.activities.incident import bootstrap_incident

    out = await bootstrap_incident({"tracking_id": "t-1", "alert": {}})
    assert out["gated"] is True
    assert out["tracking_id"] == "t-1"
    assert "CapabilityClient" in out["required_ports"]


@pytest.mark.asyncio
async def test_spt_bootstrap_gated_with_catalog(monkeypatch, tmp_path):
    monkeypatch.delenv("SUPPORT_AGENT_SPT_PARITY", raising=False)
    catalog = tmp_path / "catalog"
    (catalog / "spt").mkdir(parents=True)
    (catalog / "prompts").mkdir()
    (catalog / "spt" / "demo.json").write_text('{"id": "demo"}', encoding="utf-8")
    monkeypatch.setenv("SUPPORT_AGENT_CATALOG_ROOT", str(catalog))

    from am_support_agent.orchestrator.activities.spt import bootstrap_spt

    out = await bootstrap_spt({"demand": {"demand_ref": "d1"}})
    assert out["gated"] is True
    assert out["catalog_preview"]["spt_entry_count"] == 1


def test_worker_registers_parity_workflows():
    from am_support_agent.orchestrator.workflows import (
        AlertIncidentWorkflow,
        SptRunWorkflow,
        SupportA2AWorkflow,
    )

    assert SupportA2AWorkflow.__name__
    assert AlertIncidentWorkflow.__name__
    assert SptRunWorkflow.__name__
