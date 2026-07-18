"""Idempotent ticket / verify / infra action short-circuits (Temporal retry safety)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from am_platform_ports.fakes import (
    FakeDirectory,
    FakeDocStore,
    FakeHandoff,
    FakeInfraOps,
    FakeRunStore,
    FakeTicketStore,
    FakeToolSandbox,
)
from am_platform_ports.schemas.enums import RunKind, RunStatus
from am_platform_ports.schemas.run import CreateRunRequest
from platform_worker.activities import alert_incident as ticket_mod
from platform_worker.activities import analyze as analyze_mod
from platform_worker.activities import verify as verify_mod
from platform_worker.di import Ports, reset_ports_for_tests


def _ports(**overrides: Any) -> Ports:
    reset_ports_for_tests()
    runs = overrides.pop("runs", None) or FakeRunStore()
    base = dict(
        triage=MagicMock(),
        directory=FakeDirectory(),
        tickets=FakeTicketStore(),
        notifier=MagicMock(),
        prompts=MagicMock(),
        runs=runs,
        docs=FakeDocStore(),
        observe=MagicMock(),
        infra=FakeInfraOps(sandbox=FakeToolSandbox()),
        redactor=MagicMock(scrub=lambda payload: payload),
        llm=MagicMock(),
        mail=MagicMock(),
        handoff=FakeHandoff(runs),
        spt_catalog=MagicMock(),
        spt_resolver=MagicMock(),
        spt_policy=MagicMock(),
        spt_prep=MagicMock(),
        spt_runner=MagicMock(),
    )
    base.update(overrides)
    return Ports(**base)


@pytest.fixture(autouse=True)
def _restore_get_ports():
    originals = {
        "ticket": ticket_mod.get_ports,
        "analyze": analyze_mod.get_ports,
        "verify": verify_mod.get_ports,
    }
    yield
    ticket_mod.get_ports = originals["ticket"]  # type: ignore[attr-defined]
    analyze_mod.get_ports = originals["analyze"]  # type: ignore[attr-defined]
    verify_mod.get_ports = originals["verify"]  # type: ignore[attr-defined]
    reset_ports_for_tests()


@pytest.mark.asyncio
async def test_create_and_assign_ticket_reuses_existing_ticket_ref() -> None:
    ports = _ports()
    ticket_mod.get_ports = lambda: ports  # type: ignore[attr-defined]
    run = ports.runs.create_run(
        CreateRunRequest(kind=RunKind.ALERT_INCIDENT, status=RunStatus.ACCEPTED)
    )
    alert = {
        "summary": "redis down",
        "labels": {"env": "lab", "alertname": "KubeServiceDown"},
    }
    triage = {"priority": "P2", "summary": "redis down", "labels": alert["labels"]}

    first = await ticket_mod.create_and_assign_ticket(
        {"run_ref": run.run_ref, "triage": triage, "alert": alert, "tracking_id": "AM-1"}
    )
    assert first["reused"] == "0"
    assert first["ticket_ref"]
    created_count = len(ports.tickets.tickets)

    second = await ticket_mod.create_and_assign_ticket(
        {"run_ref": run.run_ref, "triage": triage, "alert": alert, "tracking_id": "AM-1"}
    )
    assert second["reused"] == "1"
    assert second["ticket_ref"] == first["ticket_ref"]
    assert len(ports.tickets.tickets) == created_count


@pytest.mark.asyncio
async def test_create_and_assign_ticket_short_circuits_after_create_before_assign() -> None:
    """Simulate timeout after create: ticket_ref already on run → no second create."""
    ports = _ports()
    ticket_mod.get_ports = lambda: ports  # type: ignore[attr-defined]
    run = ports.runs.create_run(
        CreateRunRequest(kind=RunKind.ALERT_INCIDENT, status=RunStatus.ACCEPTED)
    )
    ticket = ports.tickets.create(
        title="pre",
        description="d",
        priority="P3",
        labels={"env": "lab"},
    )
    ports.runs.update_run_status(
        run_ref=run.run_ref,
        status=RunStatus.RUNNING,
        summary={
            "ticket_ref": ticket.ticket_ref,
            "ticket_url": ticket.url,
            "env": "lab",
            "channel_ref": "cliq:lab",
            "assignee_ref": "user:lab",
        },
    )
    out = await ticket_mod.create_and_assign_ticket(
        {
            "run_ref": run.run_ref,
            "triage": {"priority": "P3", "summary": "x", "labels": {"env": "lab"}},
            "alert": {"summary": "x", "labels": {"env": "lab"}},
            "tracking_id": "AM-2",
        }
    )
    assert out["reused"] == "1"
    assert out["ticket_ref"] == ticket.ticket_ref
    assert len(ports.tickets.tickets) == 1


@pytest.mark.asyncio
async def test_spawn_verify_run_reuses_parent_verify_run_ref(catalog_path) -> None:
    ports = _ports()
    verify_mod.get_ports = lambda: ports  # type: ignore[attr-defined]
    parent = ports.runs.create_run(
        CreateRunRequest(kind=RunKind.ALERT_INCIDENT, status=RunStatus.RUNNING)
    )
    first = await verify_mod.spawn_verify_run(
        {
            "parent_run_ref": parent.run_ref,
            "incident_ref": "AM-3",
            "ticket_ref": "jira:X-1",
            "workflow_id": "wf-1",
        }
    )
    assert first["reused"] == "0"
    verify_runs = [r for r in ports.runs.runs.values() if r.kind == RunKind.VERIFY]
    assert len(verify_runs) == 1

    second = await verify_mod.spawn_verify_run(
        {
            "parent_run_ref": parent.run_ref,
            "incident_ref": "AM-3",
            "ticket_ref": "jira:X-1",
            "workflow_id": "wf-1",
        }
    )
    assert second["reused"] == "1"
    assert second["verify_run_ref"] == first["verify_run_ref"]
    verify_runs = [r for r in ports.runs.runs.values() if r.kind == RunKind.VERIFY]
    assert len(verify_runs) == 1


@pytest.fixture
def catalog_path(tmp_path, monkeypatch):
    path = tmp_path / "checks.yaml"
    path.write_text(
        """
checks:
  - check_ref: verify.k8s.endpoints.ready
    kind: metrics
    query_ref: k8s.endpoints.ready
    pass_when: "value > 0"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("VERIFY_CATALOG_PATH", str(path))
    return path


@pytest.mark.asyncio
async def test_execute_infra_action_reuses_passed_step() -> None:
    ports = _ports()
    analyze_mod.get_ports = lambda: ports  # type: ignore[attr-defined]
    run = ports.runs.create_run(
        CreateRunRequest(kind=RunKind.ALERT_INCIDENT, status=RunStatus.RUNNING)
    )
    payload = {
        "run_ref": run.run_ref,
        "incident_ref": "AM-4",
        "ticket_ref": "jira:X-1",
        "tool_name": "lab.mark_fixed",
        "args": {"incident_ref": "AM-4"},
        "index": 0,
        "alert": {},
        "env": "lab",
    }
    first = await analyze_mod.execute_infra_action(payload)
    assert first["ok"] is True
    assert first["reused"] is False
    work_ref = first["work_ref"]

    # Force sandbox to fail if re-executed
    original_run = ports.infra._sandbox.run

    def boom(**kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("should not re-execute")

    ports.infra._sandbox.run = boom  # type: ignore[method-assign]
    second = await analyze_mod.execute_infra_action(payload)
    ports.infra._sandbox.run = original_run  # type: ignore[method-assign]
    assert second["ok"] is True
    assert second["reused"] is True
    assert second["work_ref"] == work_ref


@pytest.mark.asyncio
async def test_create_infra_handoff_reuses_passed_step() -> None:
    ports = _ports()
    analyze_mod.get_ports = lambda: ports  # type: ignore[attr-defined]
    run = ports.runs.create_run(
        CreateRunRequest(kind=RunKind.ALERT_INCIDENT, status=RunStatus.RUNNING)
    )
    decision = {
        "decision": "auto_infra",
        "rationale": "restart",
        "handoff_agent": "kagent_infra",
        "proposed_actions": [{"tool_name": "lab.mark_fixed", "args": {}}],
    }
    payload = {
        "run_ref": run.run_ref,
        "ticket_ref": "jira:X-1",
        "decision": decision,
        "alert": {"labels": {"env": "lab"}},
        "env": "lab",
        "tracking_id": "AM-5",
    }
    first = await analyze_mod.create_infra_handoff(payload)
    assert first["ok"] is True
    assert first["reused"] is False
    handoff_ref = first["handoff_ref"]
    handoff_count = len(ports.handoff.handoffs)

    second = await analyze_mod.create_infra_handoff(payload)
    assert second["ok"] is True
    assert second["reused"] is True
    assert second["handoff_ref"] == handoff_ref
    assert len(ports.handoff.handoffs) == handoff_count


@pytest.mark.asyncio
async def test_post_cliq_update_returns_status_and_run_step() -> None:
    from am_platform_ports.fakes import FakeNotifier
    from am_platform_ports.schemas.enums import StepStatus

    notifier = FakeNotifier()
    ports = _ports(notifier=notifier)
    ticket_mod.get_ports = lambda: ports  # type: ignore[attr-defined]
    run = ports.runs.create_run(
        CreateRunRequest(kind=RunKind.ALERT_INCIDENT, status=RunStatus.RUNNING)
    )
    out = await ticket_mod.post_cliq_update(
        {
            "run_ref": run.run_ref,
            "tracking_id": "AM-NOTIFY-1",
            "phase": "INTAKE",
            "status": "INVESTIGATING",
            "channel_ref": "cliq:lab",
            "ticket_ref": "jira:X-9",
            "alert": {"summary": "disk full", "labels": {"env": "lab", "alertname": "Disk"}},
            "reason": "Ticket created",
            "env": "lab",
        }
    )
    assert out["status"] == "ok"
    assert out["cliq_ref"]
    assert out["phase"] == "INTAKE"
    assert len(notifier.sent) == 1
    steps = [s for s in ports.runs.steps.values() if s.name == "notify.cliq.intake"]
    assert len(steps) == 1
    assert steps[0].status == StepStatus.PASSED


@pytest.mark.asyncio
async def test_send_incident_mail_returns_status_and_run_step() -> None:
    from am_platform_ports.fakes import FakeMail
    from am_platform_ports.schemas.enums import StepStatus

    mail = FakeMail()
    ports = _ports(mail=mail)
    ticket_mod.get_ports = lambda: ports  # type: ignore[attr-defined]
    run = ports.runs.create_run(
        CreateRunRequest(kind=RunKind.ALERT_INCIDENT, status=RunStatus.RUNNING)
    )
    out = await ticket_mod.send_incident_mail(
        {
            "run_ref": run.run_ref,
            "tracking_id": "AM-NOTIFY-2",
            "phase": "CLOSE",
            "status": "RESOLVED",
            "ticket_ref": "jira:X-9",
            "alert": {"summary": "disk full", "labels": {"env": "lab"}},
            "assignee_email": "owner@example.com",
            "reason": "Verify passed",
            "env": "lab",
            "ended": True,
        }
    )
    assert out["status"] == "ok"
    assert out["mail_ref"]
    assert "owner@example.com" in out["recipients"]
    assert len(mail.sent) == 1
    steps = [s for s in ports.runs.steps.values() if s.name == "notify.mail.close"]
    assert len(steps) == 1
    assert steps[0].status == StepStatus.PASSED


@pytest.mark.asyncio
async def test_post_cliq_update_soft_fails_without_raising() -> None:
    notifier = MagicMock()
    notifier.send_card.side_effect = RuntimeError("cliq down")
    ports = _ports(notifier=notifier)
    ticket_mod.get_ports = lambda: ports  # type: ignore[attr-defined]
    run = ports.runs.create_run(
        CreateRunRequest(kind=RunKind.ALERT_INCIDENT, status=RunStatus.RUNNING)
    )
    out = await ticket_mod.post_cliq_update(
        {
            "run_ref": run.run_ref,
            "tracking_id": "AM-NOTIFY-3",
            "phase": "ESCALATE",
            "status": "FAILED",
            "channel_ref": "cliq:lab",
            "alert": {"summary": "x", "labels": {"env": "lab"}},
            "env": "lab",
            "ended": True,
        }
    )
    assert out["status"] == "error"
    assert "cliq down" in out["error"]
    assert out["cliq_ref"] == ""
