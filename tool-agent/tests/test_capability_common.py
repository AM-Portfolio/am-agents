from tools._shared.capability.approval import requires_write_confirmation, risk_for_operation
from tools._shared.capability.idempotency import IdempotencyStore
from tools._shared.capability.plan_binding import (
    clear_plan_bindings,
    intent_plan_hash,
    issue_plan_binding,
    verify_plan_binding,
)
from tools._shared.capability.results import normalize_result
from app.models.intent import IntentDocument


def test_risk_and_confirmation():
    assert risk_for_operation("get") == "read"
    assert risk_for_operation("create") == "create"
    assert requires_write_confirmation("create")
    assert not requires_write_confirmation("read")


def test_plan_binding_roundtrip():
    clear_plan_bindings()
    intent = IntentDocument(
        backend="work-item",
        operation="create",
        params={"title": "x"},
        read_only=False,
        confidence=1.0,
    )
    plan_hash, token, phrase = issue_plan_binding(intent)
    assert plan_hash == intent_plan_hash(intent)
    assert verify_plan_binding(token=token, phrase=phrase, intent=intent, plan_hash=plan_hash)
    assert not verify_plan_binding(token=token, phrase=phrase, intent=intent, plan_hash=plan_hash)


def test_idempotency_store():
    store = IdempotencyStore(ttl_seconds=60)
    store.put("k1", plan_hash="abc", result={"ok": True})
    assert store.get("k1", plan_hash="abc") == {"ok": True}
    assert store.get("k1", plan_hash="other") is None


def test_normalize_result_async():
    result = normalize_result(
        capability="spt.execute",
        provider="memory",
        data={"status": "running"},
        async_operation_ref="mem:spt:1",
        approval_risk="execute",
    )
    assert result["status"] == "accepted"
    assert result["async_operation_ref"] == "mem:spt:1"
