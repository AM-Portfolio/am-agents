"""InfraOps allowlist + FakeInfraOps contract tests."""

from __future__ import annotations

import pytest

from am_platform_ports.fakes import FakeInfraOps, FakeToolSandbox
from am_platform_ports.ports.infra import InfraOps
from am_platform_ports.schemas.core import InfraOpsAction, InfraOpsPlan


def test_infra_ops_plan_and_execute_allowlisted() -> None:
    infra: InfraOps = FakeInfraOps()
    plan = infra.plan(incident_ref="inc-1", context={"ticket_ref": "op:wp:1"})
    assert plan.actions
    assert plan.actions[0].tool_name == "lab.mark_fixed"
    done = infra.execute(plan=plan)
    assert done.work_ref.startswith("work-")
    assert "lab.mark_fixed" in done.actions_ran


def test_sandbox_denies_unknown_tool() -> None:
    sb = FakeToolSandbox()
    with pytest.raises(PermissionError):
        sb.run(tool_name="shell.rm_rf", args={})


def test_infra_ops_rejects_non_allowlisted_action() -> None:
    infra = FakeInfraOps()
    bad = InfraOpsPlan(
        plan_ref="plan-bad",
        actions=[InfraOpsAction(tool_name="kubectl.delete", args={"ns": "prod"})],
    )
    with pytest.raises(PermissionError):
        infra.execute(plan=bad)
