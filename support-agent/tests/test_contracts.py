"""Contract tests for A2A schemas and registry."""

from __future__ import annotations

import pytest

from am_support_agent.contracts import A2AOp, TaskRequest, TaskStatus
from am_support_agent.registry import AgentRegistry, load_registry_dict, default_registry_path


def test_registry_loads_three_agents():
    reg = AgentRegistry(load_registry_dict(default_registry_path()))
    ids = {c.agent_id for c in reg.list_cards()}
    assert ids == {"tool-agent", "db-agent", "ui-test-agent"}
    assert reg.prefer == "tool-agent"
    assert reg.platform_agent_id == "support-agent"


def test_tool_preferred_by_default():
    reg = AgentRegistry(load_registry_dict(default_registry_path()))
    card = reg.resolve_agent()
    assert card.agent_id == "tool-agent"


def test_db_requires_legacy_flag():
    reg = AgentRegistry(load_registry_dict(default_registry_path()))
    with pytest.raises(PermissionError):
        reg.resolve_agent(agent_id="db-agent")
    card = reg.resolve_agent(agent_id="db-agent", require_legacy_db=True)
    assert card.agent_id == "db-agent"


def test_ui_capability_routes_to_ui_agent():
    reg = AgentRegistry(load_registry_dict(default_registry_path()))
    card = reg.resolve_agent(capability_prefix="ui.test.run")
    assert card.agent_id == "ui-test-agent"


def test_task_request_roundtrip():
    req = TaskRequest(
        task_id="t1",
        agent_id="tool-agent",
        op=A2AOp.EXECUTE,
        idempotency_key="idem-1",
        payload={"tool": "grafana.query"},
    )
    data = req.model_dump()
    again = TaskRequest.model_validate(data)
    assert again.op == A2AOp.EXECUTE
    assert again.idempotency_key == "idem-1"


def test_task_status_enum():
    assert TaskStatus.SUCCEEDED.value == "succeeded"


def test_capability_ids_are_vendor_free():
    from am_support_agent.contracts import CapabilityId

    values = {item.value for item in CapabilityId}
    joined = " ".join(values).lower()
    for vendor in ("openproject", "jira", "zoho", "cliq", "minio", "k6"):
        assert vendor not in joined
    assert CapabilityId.WORK_ITEM_GET.value == "work-item.get"
    assert CapabilityId.SPT_EXECUTE.value == "spt.execute"


def test_incident_validation_gate_roundtrip():
    from am_support_agent.contracts import (
        IncidentContext,
        IncidentValidation,
        IncidentValidationStatus,
        WorkItemRef,
    )

    ctx = IncidentContext(
        tracking_id="trk-1",
        run_ref="run-1",
        work_item=WorkItemRef(
            work_item_ref="WI-1",
            assignee_ref="user:1",
            correlation_id="trk-1",
        ),
    )
    validation = IncidentValidation(
        status=IncidentValidationStatus.INCONCLUSIVE,
        confidence=0.4,
        reasons=["missing_metrics_window"],
        missing_evidence=["observe.metrics.query"],
        work_item_ok=True,
    )
    again = IncidentValidation.model_validate(validation.model_dump())
    assert again.status == IncidentValidationStatus.INCONCLUSIVE
    assert IncidentContext.model_validate(ctx.model_dump()).work_item.work_item_ref == "WI-1"


def test_capability_call_carries_approval_and_idempotency():
    from am_support_agent.contracts import (
        ApprovalMetadata,
        ApprovalRisk,
        CapabilityCall,
        CapabilityId,
        IdempotencyMetadata,
    )

    call = CapabilityCall(
        capability=CapabilityId.WORK_ITEM_CREATE.value,
        args={"title": "alert"},
        approval=ApprovalMetadata(risk=ApprovalRisk.CREATE),
        idempotency=IdempotencyMetadata(key="idem-1", plan_hash="abc"),
    )
    assert call.approval.risk == ApprovalRisk.CREATE
    assert call.idempotency.key == "idem-1"
