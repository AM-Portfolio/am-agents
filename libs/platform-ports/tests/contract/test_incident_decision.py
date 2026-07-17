"""Incident decision policy + FakeLlm routing tests."""

from __future__ import annotations

import json
import os

import pytest

from am_platform_ports.fakes import FakeLlm
from am_platform_ports.policy.incident_actions import enforce_decision, filter_actions
from am_platform_ports.schemas.incident import IncidentDecision, ProposedAction


def test_delete_action_rejected() -> None:
    allowed, rejected = filter_actions(
        [ProposedAction(tool_name="k8s.delete_pod", args={}), ProposedAction(tool_name="lab.pod_status")]
    )
    assert [a.tool_name for a in allowed] == ["lab.pod_status"]
    assert any("denied" in r or "not_allowlisted" in r for r in rejected)


def test_enforce_delete_attempt_becomes_needs_human() -> None:
    raw = IncidentDecision(
        decision="auto_infra",
        confidence=0.99,
        rationale="bad",
        proposed_actions=[ProposedAction(tool_name="k8s.delete_deployment", args={})],
    )
    out = enforce_decision(raw)
    assert out.decision == "needs_human"


def test_enforce_auto_infra_keeps_safe_tools() -> None:
    raw = IncidentDecision(
        decision="auto_infra",
        confidence=0.9,
        rationale="pod down",
        handoff_agent="kagent_infra",
        proposed_actions=[
            ProposedAction(tool_name="lab.pod_status", args={"ns": "lab"}),
            ProposedAction(tool_name="lab.pod_restart", args={"ns": "lab"}),
        ],
    )
    out = enforce_decision(raw)
    assert out.decision == "auto_infra"
    assert out.handoff_agent == "kagent_infra"
    assert len(out.proposed_actions) == 2


def test_low_confidence_escalates() -> None:
    raw = IncidentDecision(decision="auto_infra", confidence=0.1, rationale="unsure")
    out = enforce_decision(raw)
    assert out.decision == "needs_human"


def test_fake_llm_force_decisions(monkeypatch: pytest.MonkeyPatch) -> None:
    llm = FakeLlm()
    monkeypatch.setenv("ALERT_FORCE_DECISION", "ignore")
    d = json.loads(llm.complete(prompt_key="incident.analyze", variables={}))
    assert d["decision"] == "ignore"

    monkeypatch.setenv("ALERT_FORCE_DECISION", "auto_infra")
    d = json.loads(llm.complete(prompt_key="incident.analyze", variables={}))
    assert d["decision"] == "auto_infra"
    enforced = enforce_decision(IncidentDecision.model_validate(d))
    assert enforced.decision == "auto_infra"

    monkeypatch.setenv("ALERT_FORCE_DECISION", "delete_attempt")
    d = json.loads(llm.complete(prompt_key="incident.analyze", variables={}))
    enforced = enforce_decision(IncidentDecision.model_validate(d))
    assert enforced.decision == "needs_human"
