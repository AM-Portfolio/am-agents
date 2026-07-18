"""Composition root and port adapter tests."""

from __future__ import annotations

import httpx
import pytest

from am_support_agent.adapters.capability_client import ToolAgentCapabilityClient
from am_support_agent.adapters.documents import MemoryDocumentStore
from am_support_agent.adapters.llm import FakeLlmClient
from am_support_agent.composition import build_runtime
from am_support_agent.contracts.capabilities import (
    ApprovalMetadata,
    CapabilityCall,
    IdempotencyMetadata,
)
from am_support_agent.contracts.enums import ApprovalRisk
from am_support_agent.ports.clock import SystemClock, UuidGenerator


def test_build_runtime_test_mode(monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_RUNTIME_MODE", "test")
    monkeypatch.delenv("SUPPORT_AGENT_REQUIRE_LIVE_ADAPTERS", raising=False)
    rt = build_runtime(mode="test")
    readiness = rt.readiness()
    assert readiness["ready"] is True
    assert rt.capability.status()["wired"] is True
    assert rt.documents.status()["wired"] is True
    assert rt.llm.status()["wired"] is True  # FakeLlmClient in test mode
    assert rt.semantic.status()["deferred"] is True


def test_require_live_adapters_fail_closed(monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_REQUIRE_LIVE_ADAPTERS", "true")
    monkeypatch.setenv("SUPPORT_AGENT_DOC_PROVIDER", "minio")
    monkeypatch.delenv("MINIO_ENDPOINT", raising=False)
    monkeypatch.delenv("MINIO_ACCESS_KEY", raising=False)
    monkeypatch.delenv("MINIO_SECRET_KEY", raising=False)
    rt = build_runtime(mode="prod")
    readiness = rt.readiness()
    assert readiness["ready"] is False
    assert "documents" in readiness["missing"]


@pytest.mark.asyncio
async def test_memory_document_store_roundtrip():
    store = MemoryDocumentStore()
    ref = await store.put(object_key="runs/a.json", content=b'{"ok":true}', content_type="application/json")
    assert ref.object_key.endswith("runs/a.json")
    assert await store.exists(object_key="runs/a.json")
    assert await store.get(object_key="runs/a.json") == b'{"ok":true}'


@pytest.mark.asyncio
async def test_fake_llm_and_clock():
    llm = FakeLlmClient(reply="hello")
    out = await llm.complete(system="s", user="u", prompt_key="k")
    assert out.text == "hello"
    assert out.gated is False
    assert SystemClock().now_iso()
    assert UuidGenerator().new_id("run-").startswith("run-")


@pytest.mark.asyncio
async def test_capability_client_plan_execute(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/plan"):
            return httpx.Response(
                200,
                json={
                    "plan_hash": "abc",
                    "requires_write_confirmation": True,
                    "confirmation_token": "tok",
                    "confirmation_phrase": "CONFIRM WORK-ITEM WRITE 123",
                    "intent": {
                        "backend": "work-item",
                        "operation": "create",
                        "params": {"title": "t"},
                        "read_only": False,
                        "confidence": 1.0,
                    },
                },
            )
        if request.url.path.endswith("/execute"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "ok": True,
                        "provider": "memory",
                        "data": {"work_item_ref": "mem:wi:1"},
                    }
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="http://tool.test")
    cap = ToolAgentCapabilityClient(base_url="http://tool.test", client=client)
    result = await cap.call(
        CapabilityCall(
            capability="work-item.create",
            args={"title": "t"},
            approval=ApprovalMetadata(risk=ApprovalRisk.CREATE),
            idempotency=IdempotencyMetadata(key="k1"),
        )
    )
    assert result.ok is True
    assert result.capability == "work-item.create"
    await client.aclose()
