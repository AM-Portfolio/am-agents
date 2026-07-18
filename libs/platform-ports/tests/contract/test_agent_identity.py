"""Tests for IT-Support-agent identity + multi-env helpers."""

from __future__ import annotations

from am_platform_ports.agent_identity import (
    agent_prefix,
    cliq_channel_for_env,
    ensure_env_label,
    normalize_alert_env,
    title_with_env,
    verify_force_allowed,
)
from am_platform_ports.policy.incident_actions import enforce_decision
from am_platform_ports.schemas.incident import IncidentDecision, ProposedAction


def test_normalize_env_from_label() -> None:
    assert normalize_alert_env(labels={"env": "preprod"}) == "preprod"
    assert normalize_alert_env(labels={"env": "production"}) == "prod"


def test_normalize_env_from_namespace() -> None:
    assert normalize_alert_env(labels={"namespace": "am-apps-prod"}) == "prod"
    assert normalize_alert_env(labels={"namespace": "am-apps-preprod"}) == "preprod"
    assert normalize_alert_env(labels={"namespace": "infra"}) == "lab"


def test_ensure_env_label_mutates_copy() -> None:
    alert = {"summary": "x", "labels": {"namespace": "am-apps-dev"}}
    out = ensure_env_label(alert)
    assert out["labels"]["env"] == "dev"
    assert "env" not in (alert.get("labels") or {})


def test_cliq_channel_prod_vs_lab() -> None:
    assert cliq_channel_for_env("lab") == "cliq:lab"
    assert cliq_channel_for_env("prod") == "cliq:prod"


def test_agent_prefix_and_title() -> None:
    assert "IT-Support-agent" in agent_prefix(env="preprod", decision="auto_infra")
    assert title_with_env("preprod", "redis down").startswith("[preprod]")


def test_verify_force_lab_only(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_VERIFY_FORCE_ENVS", raising=False)
    assert verify_force_allowed("lab") is True
    assert verify_force_allowed("prod") is False


def test_auto_infra_blocked_in_prod_by_default() -> None:
    raw = IncidentDecision(
        decision="auto_infra",
        confidence=0.9,
        rationale="restart",
        proposed_actions=[ProposedAction(tool_name="lab.pod_status", args={})],
    )
    out = enforce_decision(raw, env="prod")
    assert out.decision == "needs_human"
    assert "auto_infra not enabled" in out.rationale


def test_auto_infra_allowed_in_preprod() -> None:
    raw = IncidentDecision(
        decision="auto_infra",
        confidence=0.9,
        rationale="restart",
        proposed_actions=[ProposedAction(tool_name="lab.pod_status", args={})],
    )
    out = enforce_decision(raw, env="preprod")
    assert out.decision == "auto_infra"
