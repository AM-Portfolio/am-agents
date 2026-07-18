"""Catalog, storage, learning, and integration boundary tests."""

from __future__ import annotations

import pytest

from am_support_agent.adapters.llm import complete_gated, llm_status
from am_support_agent.adapters.storage import (
    DocStoreNamespace,
    legacy_postgres_runstore_compatible,
)
from am_support_agent.intelligence import CatalogReader
from am_support_agent.integrations import kagent_integration_status
from am_support_agent.learning import ingest_feedback_event, promotion_allowed


def test_catalog_reader_summary(tmp_path, monkeypatch):
    root = tmp_path / "catalog"
    (root / "prompts").mkdir(parents=True)
    (root / "verify").mkdir()
    (root / "spt").mkdir()
    (root / "prompts" / "a.md").write_text("hi", encoding="utf-8")
    (root / "spt" / "one.json").write_text('{"id":"one"}', encoding="utf-8")
    monkeypatch.setenv("SUPPORT_AGENT_CATALOG_ROOT", str(root))

    summary = CatalogReader.from_env().summary()
    assert summary["available"] is True
    assert summary["prompts"] == 1
    assert summary["spt"] == 1
    assert summary["write_policy"] == "read_only_until_promotion_gate"


def test_docstore_prefix_refuses_legacy(monkeypatch):
    ns = DocStoreNamespace()
    monkeypatch.setenv("SUPPORT_AGENT_DOC_PREFIX", "support-agent-v2")
    assert ns.object_key("runs/a.json") == "support-agent-v2/runs/a.json"
    monkeypatch.setenv("SUPPORT_AGENT_DOC_PREFIX", "agent-platform/")
    with pytest.raises(ValueError, match="refusing"):
        ns.prefix()
    assert legacy_postgres_runstore_compatible() is False


def test_learning_never_auto_promotes():
    assert promotion_allowed(human_approved=False, offline_eval_passed=True) is False
    assert promotion_allowed(human_approved=True, offline_eval_passed=False) is False
    assert promotion_allowed(human_approved=True, offline_eval_passed=True) is True
    event = ingest_feedback_event({"rating": "pass"})
    assert event["auto_promote"] is False


@pytest.mark.asyncio
async def test_llm_and_kagent_gates(monkeypatch):
    monkeypatch.delenv("SUPPORT_AGENT_LLM_ENABLED", raising=False)
    status = llm_status()
    assert status["wired"] is False
    gated = await complete_gated("hello")
    assert gated["gated"] is True
    k = kagent_integration_status()
    assert k["in_orchestrator_binary"] is False
    assert k["executor"] == "tool-agent"
