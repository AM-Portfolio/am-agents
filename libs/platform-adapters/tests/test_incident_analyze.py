"""File prompt registry + analyze activity (no Temporal)."""

from __future__ import annotations

from pathlib import Path

import pytest

from am_platform_adapters.prompt_registry import FilePromptRegistry
from am_platform_ports.schemas.enums import RunKind
from am_platform_ports.schemas.run import CreateRunRequest

ROOT = Path(__file__).resolve().parents[3] / "catalog" / "prompts"


def test_file_prompt_registry_loads_analyze() -> None:
    reg = FilePromptRegistry(ROOT)
    p = reg.get(prompt_key="incident.analyze")
    assert "needs_human" in p["system"]
    assert "auto_infra" in p["system"]
    esc = reg.get(prompt_key="incident.escalate_unsolved")
    assert "could not fully solve" in esc["system"]


@pytest.mark.asyncio
async def test_analyze_incident_activity_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("PROMPT_PROVIDER", "fake")
    monkeypatch.setenv("RUN_STORE_PROVIDER", "fake")

    from platform_worker import di
    from platform_worker.activities import analyze as aan

    monkeypatch.setenv("ALERT_FORCE_DECISION", "auto_infra")
    di.reset_ports_for_tests()
    ports = di.get_ports()
    run = ports.runs.create_run(CreateRunRequest(kind=RunKind.ALERT_INCIDENT, incident_ref="t1"))
    out = await aan.analyze_incident(
        {
            "run_ref": run.run_ref,
            "alert": {
                "summary": "PodNotReady",
                "priority": "P2",
                "labels": {"alertname": "PodNotReady", "namespace": "lab"},
            },
        }
    )
    assert out["decision"] == "auto_infra"
    assert out["proposed_actions"]

    monkeypatch.setenv("ALERT_FORCE_DECISION", "ignore")
    di.reset_ports_for_tests()
    ports = di.get_ports()
    run = ports.runs.create_run(CreateRunRequest(kind=RunKind.ALERT_INCIDENT, incident_ref="t2"))
    out = await aan.analyze_incident({"run_ref": run.run_ref, "alert": {"summary": "noise"}})
    assert out["decision"] == "ignore"

    monkeypatch.setenv("ALERT_FORCE_DECISION", "delete_attempt")
    di.reset_ports_for_tests()
    ports = di.get_ports()
    run = ports.runs.create_run(CreateRunRequest(kind=RunKind.ALERT_INCIDENT, incident_ref="t3"))
    out = await aan.analyze_incident({"run_ref": run.run_ref, "alert": {"summary": "x"}})
    assert out["decision"] == "needs_human"


@pytest.mark.asyncio
async def test_handoff_infra_runs_allowlisted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("ALERT_FORCE_DECISION", "auto_infra")
    monkeypatch.setenv("PROMPT_PROVIDER", "fake")
    monkeypatch.setenv("RUN_STORE_PROVIDER", "fake")
    monkeypatch.setenv("ALERT_NOTIFY_PROVIDER", "fake")
    monkeypatch.delenv("INFRA_FORCE_FAIL", raising=False)

    from platform_worker import di
    from platform_worker.activities import analyze as aan

    di.reset_ports_for_tests()
    ports = di.get_ports()
    run = ports.runs.create_run(CreateRunRequest(kind=RunKind.ALERT_INCIDENT, incident_ref="h1"))
    decision = await aan.analyze_incident({"run_ref": run.run_ref, "alert": {"summary": "pod"}})
    out = await aan.handoff_infra_agent(
        {
            "run_ref": run.run_ref,
            "incident_ref": "h1",
            "ticket_ref": "ticket-x",
            "alert": {},
            "decision": decision,
        }
    )
    assert out["ok"] is True
    assert out["handoff_ref"]
    assert "lab.pod_status" in out["actions_ran"] or "lab.pod_restart" in out["actions_ran"]


@pytest.mark.asyncio
async def test_handoff_fail_then_escalate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("ALERT_FORCE_DECISION", "auto_infra")
    monkeypatch.setenv("PROMPT_PROVIDER", "fake")
    monkeypatch.setenv("RUN_STORE_PROVIDER", "fake")
    monkeypatch.setenv("ALERT_NOTIFY_PROVIDER", "fake")
    monkeypatch.setenv("TICKET_PROVIDER", "fake")
    monkeypatch.setenv("INFRA_FORCE_FAIL", "1")

    from platform_worker import di
    from platform_worker.activities import analyze as aan
    from am_platform_ports.schemas.enums import RunKind, RunStatus
    from am_platform_ports.schemas.run import CreateRunRequest

    di.reset_ports_for_tests()
    ports = di.get_ports()
    run = ports.runs.create_run(CreateRunRequest(kind=RunKind.ALERT_INCIDENT, incident_ref="fail1"))
    ticket = ports.tickets.create(title="t", description="d", priority="P2")
    decision = await aan.analyze_incident({"run_ref": run.run_ref, "alert": {"summary": "pod"}})
    infra = await aan.handoff_infra_agent(
        {
            "run_ref": run.run_ref,
            "incident_ref": "fail1",
            "ticket_ref": ticket.ticket_ref,
            "alert": {},
            "decision": decision,
        }
    )
    assert infra["ok"] is False
    assert infra["attempts"]
    assert infra["failure_reason"]

    esc = await aan.escalate_unsolved(
        {
            "run_ref": run.run_ref,
            "ticket_ref": ticket.ticket_ref,
            "channel_ref": "cliq:lab",
            "decision": decision,
            "attempts": infra["attempts"],
            "failure_reason": infra["failure_reason"],
            "verify_status": "",
            "extra": "test",
        }
    )
    assert esc["status"] == "needs_human"
    updated = ports.runs.get_run(run_ref=run.run_ref)
    assert updated is not None and updated.status == RunStatus.NEEDS_HUMAN
    assert any("unsolved" in c for c in ports.tickets.tickets[ticket.ticket_ref]["comments"])
    assert ports.notifier.sent
