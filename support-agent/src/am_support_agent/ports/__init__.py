"""Support-agent ports — orchestration-facing contracts (no vendor SDKs)."""

from am_support_agent.ports.capability import CapabilityClient, CapabilityResult
from am_support_agent.ports.catalog import CatalogStore
from am_support_agent.ports.clock import Clock, IdGenerator, SystemClock, UuidGenerator
from am_support_agent.ports.documents import DocumentStore
from am_support_agent.ports.llm import LlmClient, LlmCompletion
from am_support_agent.ports.prompts import PromptRegistry, ResolvedPrompt
from am_support_agent.ports.semantic import SemanticIndex

__all__ = [
    "CapabilityClient",
    "CapabilityResult",
    "CatalogStore",
    "Clock",
    "DocumentStore",
    "IdGenerator",
    "LlmClient",
    "LlmCompletion",
    "PromptRegistry",
    "ResolvedPrompt",
    "SemanticIndex",
    "SystemClock",
    "UuidGenerator",
]
