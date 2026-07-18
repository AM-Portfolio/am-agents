"""HandoffPort contract tests."""

import pytest

from am_platform_ports.fakes import FakeHandoff, FakeRunStore
from am_platform_ports.schemas.enums import RunKind, RunStatus
from am_platform_ports.schemas.run import CreateRunRequest


def test_handoff_max_depth_1() -> None:
    rs = FakeRunStore()
    parent = rs.create_run(CreateRunRequest(kind=RunKind.ALERT_INCIDENT, incident_ref="i1"))
    h = FakeHandoff(rs)
    child = h.handoff(from_run_ref=parent.run_ref, to_kind="spt", depth=1)
    assert child.startswith("run-")
    assert rs.get_run(run_ref=child).kind == RunKind.HANDOFF
    assert rs.get_run(run_ref=child).parent_run_ref == parent.run_ref

    with pytest.raises(PermissionError, match="MAX_DEPTH"):
        h.handoff(from_run_ref=child, to_kind="verify", depth=2)


def test_handoff_unknown_parent() -> None:
    h = FakeHandoff()
    with pytest.raises(KeyError):
        h.handoff(from_run_ref="missing", to_kind="spt", depth=1)
