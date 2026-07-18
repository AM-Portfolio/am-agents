"""Planner unit tests."""

from __future__ import annotations

import pytest

from am_support_agent.contracts.enums import A2AOp
from am_support_agent.orchestrator import Planner, PlannedTask
from am_support_agent.registry import AgentRegistry, default_registry_path, load_registry_dict


def test_planner_prefers_tool_and_limits_fanout():
    reg = AgentRegistry(load_registry_dict(default_registry_path()))
    planner = Planner(reg)
    plan = planner.plan(
        correlation_id="c1",
        tasks=[
            PlannedTask(agent_id="", capability="tools.execute", op=A2AOp.EXECUTE, payload={}),
        ],
    )
    assert plan.tasks[0].agent_id == "tool-agent"
    reqs = planner.to_requests(plan)
    assert len(reqs) == 1
    assert reqs[0].idempotency_key


def test_planner_rejects_over_fanout():
    reg = AgentRegistry(load_registry_dict(default_registry_path()))
    planner = Planner(reg)
    tasks = [
        PlannedTask(agent_id="tool-agent", capability="tools.execute", op=A2AOp.EXECUTE)
        for _ in range(20)
    ]
    with pytest.raises(ValueError, match="fanout"):
        planner.plan(correlation_id="c", tasks=tasks)
