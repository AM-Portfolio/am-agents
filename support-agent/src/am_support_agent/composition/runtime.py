"""Single composition root for support-agent ports."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from am_support_agent.adapters.capability_client import (
    FakeCapabilityClient,
    ToolAgentCapabilityClient,
)
from am_support_agent.adapters.catalog_store import FileCatalogStore, StubSemanticIndex
from am_support_agent.adapters.documents import MemoryDocumentStore, MinioDocumentStore
from am_support_agent.adapters.llm import FakeLlmClient, GatedLlmClient, HttpLlmClient, llm_enabled
from am_support_agent.adapters.prompts import FilePromptRegistry, LangfusePromptRegistry
from am_support_agent.adapters.security import Redactor, SandboxPolicy, SecretBroker
from am_support_agent.adapters.storage import DocStoreNamespace
from am_support_agent.learning import configure_learning
from am_support_agent.ports.capability import CapabilityClient
from am_support_agent.ports.catalog import CatalogStore
from am_support_agent.ports.clock import Clock, IdGenerator, SystemClock, UuidGenerator
from am_support_agent.ports.documents import DocumentStore
from am_support_agent.ports.episodes import EpisodeStore, FeedbackStore
from am_support_agent.ports.llm import LlmClient
from am_support_agent.ports.prompts import PromptRegistry
from am_support_agent.ports.semantic import SemanticIndex
from am_support_agent.stores.episodes import build_episode_store, build_feedback_store
from am_support_agent.stores.workflow_ledger import WorkflowLedger, build_workflow_ledger


@dataclass
class SupportRuntime:
    """Composable dependencies for gateway, worker, and activities."""

    mode: str
    capability: CapabilityClient
    llm: LlmClient
    documents: DocumentStore
    catalog: CatalogStore
    prompts: PromptRegistry
    semantic: SemanticIndex
    workflow_ledger: WorkflowLedger
    episodes: EpisodeStore
    feedback: FeedbackStore
    redactor: Redactor = field(default_factory=Redactor)
    secrets: SecretBroker = field(default_factory=SecretBroker)
    sandbox: SandboxPolicy = field(default_factory=SandboxPolicy)
    clock: Clock = field(default_factory=SystemClock)
    ids: IdGenerator = field(default_factory=UuidGenerator)

    def readiness(self) -> dict[str, Any]:
        components = {
            "capability": self.capability.status(),
            "llm": self.llm.status(),
            "documents": self.documents.status(),
            "catalog": self.catalog.status(),
            "prompts": self.prompts.status(),
            "semantic": self.semantic.status(),
            "workflow_ledger": {
                "name": type(self.workflow_ledger).__name__,
                "wired": True,
                "durable": type(self.workflow_ledger).__name__.startswith("Postgres"),
                "ready": self.workflow_ledger.ready(),
            },
            "episodes": self.episodes.status(),
            "feedback": self.feedback.status(),
            "redactor": self.redactor.status(),
            "secrets": self.secrets.status(),
            "sandbox": self.sandbox.status(),
        }
        require_live = os.getenv("SUPPORT_AGENT_REQUIRE_LIVE_ADAPTERS", "").lower() in {
            "1",
            "true",
            "yes",
        }
        missing: list[str] = []
        if require_live:
            for key in ("capability", "documents", "prompts", "catalog"):
                if not components[key].get("wired"):
                    missing.append(key)
            for key in ("episodes", "feedback", "workflow_ledger"):
                info = components[key]
                if not info.get("durable") or not info.get("ready", True):
                    missing.append(key)
            if self.mode == "prod" and not components["llm"].get("wired") and os.getenv(
                "SUPPORT_AGENT_LLM_ENABLED", ""
            ).lower() in {"1", "true", "yes"}:
                missing.append("llm")
        ready = not missing
        return {
            "ready": ready,
            "mode": self.mode,
            "require_live_adapters": require_live,
            "missing": missing,
            "components": components,
        }


def _runtime_mode() -> str:
    raw = (os.getenv("SUPPORT_AGENT_RUNTIME_MODE") or "dev").strip().lower()
    if raw in {"prod", "production"}:
        return "prod"
    if raw in {"test", "ci"}:
        return "test"
    return "dev"


def _build_documents(*, mode: str) -> DocumentStore:
    provider = (os.getenv("SUPPORT_AGENT_DOC_PROVIDER") or "").strip().lower()
    ns = DocStoreNamespace()
    if provider == "minio" or (mode == "prod" and provider != "memory"):
        store = MinioDocumentStore(namespace=ns)
        if store.status().get("wired"):
            return store
        if mode == "prod" and os.getenv("SUPPORT_AGENT_REQUIRE_LIVE_ADAPTERS", "").lower() in {
            "1",
            "true",
            "yes",
        }:
            return store
        return MemoryDocumentStore(namespace=ns)
    return MemoryDocumentStore(namespace=ns)


def _build_llm(*, mode: str) -> LlmClient:
    from am_support_agent.adapters.llm import get_env_var
    provider = (get_env_var("SUPPORT_AGENT_LLM_PROVIDER") or "").strip().lower()
    if provider == "fake" or mode == "test":
        return FakeLlmClient()
    if provider == "litellm" or (llm_enabled() and get_env_var("LITELLM_MASTER_KEY")):
        return HttpLlmClient()
    return GatedLlmClient()


def _build_capability(*, mode: str) -> CapabilityClient:
    provider = (os.getenv("SUPPORT_AGENT_CAPABILITY_PROVIDER") or "").strip().lower()
    if provider == "fake" or mode == "test":
        return FakeCapabilityClient()
    return ToolAgentCapabilityClient()


def _build_prompts() -> PromptRegistry:
    source = (os.getenv("SUPPORT_AGENT_PROMPT_SOURCE") or "file").strip().lower()
    file_reg = FilePromptRegistry()
    if source == "langfuse":
        return LangfusePromptRegistry(fallback=file_reg)
    return file_reg


def build_runtime(
    *,
    mode: str | None = None,
    workflow_ledger: WorkflowLedger | None = None,
    capability: CapabilityClient | None = None,
    llm: LlmClient | None = None,
    documents: DocumentStore | None = None,
    catalog: CatalogStore | None = None,
    prompts: PromptRegistry | None = None,
    semantic: SemanticIndex | None = None,
    episodes: EpisodeStore | None = None,
    feedback: FeedbackStore | None = None,
) -> SupportRuntime:
    resolved_mode = mode or _runtime_mode()
    episode_store = episodes or build_episode_store()
    feedback_store = feedback or build_feedback_store()
    configure_learning(episodes=episode_store, feedback=feedback_store)
    return SupportRuntime(
        mode=resolved_mode,
        capability=capability or _build_capability(mode=resolved_mode),
        llm=llm or _build_llm(mode=resolved_mode),
        documents=documents or _build_documents(mode=resolved_mode),
        catalog=catalog or FileCatalogStore(),
        prompts=prompts or _build_prompts(),
        semantic=semantic or StubSemanticIndex(),
        workflow_ledger=workflow_ledger or build_workflow_ledger(),
        episodes=episode_store,
        feedback=feedback_store,
    )


__all__ = ["SupportRuntime", "build_runtime"]
