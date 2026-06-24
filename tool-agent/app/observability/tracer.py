"""Minimal Langfuse tracer for tool-agent."""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.observability.sanitize import sanitize_payload

logger = logging.getLogger(__name__)


class ToolAgentTracer:
    def __init__(self) -> None:
        self.enabled = settings.LANGFUSE_ENABLED

    async def start_trace(
        self,
        trace_id: str,
        *,
        query: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self.enabled:
            return
        logger.debug("trace start %s query=%s meta=%s", trace_id, query[:120], metadata)

    async def end_trace(self, trace_id: str, *, output: Any = None, error: str | None = None, **kwargs: Any) -> None:
        if not self.enabled:
            return
        logger.debug("trace end %s error=%s", trace_id, error)

    async def span(
        self,
        trace_id: str,
        name: str,
        *,
        input: Any = None,
        output: Any = None,
        metadata: dict[str, Any] | None = None,
        level: str = "DEFAULT",
    ) -> None:
        if not self.enabled:
            return
        _ = sanitize_payload(input)
        logger.debug("span %s %s level=%s", trace_id, name, level)


tracer = ToolAgentTracer()


async def start_worker() -> None:
    return None


async def stop_worker() -> None:
    return None
