"""Langfuse tracing for tool-agent via public ingestion API."""

from __future__ import annotations

import asyncio
import base64
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings
from app.observability.sanitize import sanitize_payload
from app.observability.trace_labels import trace_metadata, trace_name, trace_tags

logger = logging.getLogger(__name__)

_trace_queue: asyncio.Queue[dict[str, Any]] | None = None
_worker_task: asyncio.Task | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ToolAgentTracer:
    def __init__(self) -> None:
        self.enabled = settings.LANGFUSE_ENABLED

    def _auth_header(self) -> str | None:
        if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
            return None
        token = f"{settings.LANGFUSE_PUBLIC_KEY}:{settings.LANGFUSE_SECRET_KEY}"
        return base64.b64encode(token.encode()).decode()

    async def start_trace(
        self,
        trace_id: str,
        *,
        query: str,
        metadata: dict[str, Any] | None = None,
        name: str | None = None,
        tags: list[str] | None = None,
    ) -> None:
        if not self.enabled:
            return
        meta = {"source": "tool-agent", **(metadata or {})}
        backend_hint = meta.get("backend_hint") or meta.get("backend")
        trace_title = name or trace_name(
            backend_hint if isinstance(backend_hint, str) else None,
            meta.get("operation") if isinstance(meta.get("operation"), str) else None,
            pending=True,
        )
        trace_tag_list = tags or trace_tags(
            backend_hint if isinstance(backend_hint, str) else None,
            meta.get("operation") if isinstance(meta.get("operation"), str) else None,
            parse_source=meta.get("parse_source") if isinstance(meta.get("parse_source"), str) else None,
            agent_caller=meta.get("agent_caller") if isinstance(meta.get("agent_caller"), str) else None,
        )
        await self._enqueue_trace(
            trace_id,
            name=trace_title,
            tags=trace_tag_list,
            input=sanitize_payload({"query": query}),
            metadata=meta,
        )

    def _trace_body(
        self,
        trace_id: str,
        *,
        name: str,
        tags: list[str],
        metadata: dict[str, Any],
        input: Any = None,
        output: Any = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "id": trace_id,
            "name": name,
            "userId": "tool-agent",
            "sessionId": trace_id,
            "tags": tags,
            "metadata": metadata,
        }
        if input is not None:
            body["input"] = input
        if output is not None:
            body["output"] = output
        return body

    async def _enqueue_trace(
        self,
        trace_id: str,
        *,
        name: str,
        tags: list[str],
        metadata: dict[str, Any],
        input: Any = None,
        output: Any = None,
    ) -> None:
        await self._enqueue(
            {
                "type": "trace-create",
                "body": self._trace_body(
                    trace_id,
                    name=name,
                    tags=tags,
                    metadata=metadata,
                    input=input,
                    output=output,
                ),
            }
        )

    async def span(
        self,
        trace_id: str,
        name: str,
        *,
        input: Any = None,
        output: Any = None,
        metadata: dict[str, Any] | None = None,
        level: str = "DEFAULT",
        status_message: str | None = None,
    ) -> str | None:
        if not self.enabled:
            return None
        span_id = str(uuid.uuid4())
        now = _now_iso()
        body: dict[str, Any] = {
            "id": span_id,
            "traceId": trace_id,
            "name": name,
            "startTime": now,
            "endTime": now,
            "input": sanitize_payload(input, max_chars=settings.LANGFUSE_TRACE_MAX_OUTPUT_CHARS)
            if input is not None
            else None,
            "output": sanitize_payload(output, max_chars=settings.LANGFUSE_TRACE_MAX_OUTPUT_CHARS)
            if output is not None
            else None,
            "metadata": {"source": "tool-agent", **(metadata or {})},
            "level": level,
        }
        if status_message:
            body["statusMessage"] = status_message
        await self._enqueue({"type": "span-create", "body": body})
        return span_id

    async def generation(
        self,
        trace_id: str,
        name: str,
        *,
        model: str,
        input: Any,
        output: str,
        usage: dict[str, int] | None = None,
        cost_usd: float | None = None,
        latency_ms: int | None = None,
        parent_observation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        if not self.enabled:
            return None
        generation_id = str(uuid.uuid4())
        now = _now_iso()
        meta = {"source": "tool-agent", **(metadata or {})}
        if latency_ms is not None:
            meta["latency_ms"] = latency_ms
        body: dict[str, Any] = {
            "id": generation_id,
            "traceId": trace_id,
            "name": name,
            "model": model,
            "startTime": now,
            "endTime": now,
            "input": sanitize_payload(input, max_chars=settings.LANGFUSE_TRACE_MAX_OUTPUT_CHARS),
            "output": sanitize_payload(output, max_chars=settings.LANGFUSE_TRACE_MAX_OUTPUT_CHARS),
            "metadata": meta,
        }
        if parent_observation_id:
            body["parentObservationId"] = parent_observation_id
        if usage:
            body["usageDetails"] = {
                "input": usage.get("prompt_tokens", 0),
                "output": usage.get("completion_tokens", 0),
                "total": usage.get("total_tokens", 0),
            }
        if cost_usd is not None:
            body["costDetails"] = {"total": cost_usd}
        await self._enqueue({"type": "generation-create", "body": body})
        return generation_id

    async def end_trace(
        self,
        trace_id: str,
        *,
        output: Any = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
        name: str | None = None,
        tags: list[str] | None = None,
        backend: str | None = None,
        operation: str | None = None,
        parse_source: str | None = None,
        agent_caller: str | None = None,
    ) -> None:
        if not self.enabled:
            return
        extra = dict(metadata or {})
        if error:
            extra["error"] = error
        if backend is None and isinstance(extra.get("backend"), str):
            backend = extra["backend"]
        if operation is None and isinstance(extra.get("operation"), str):
            operation = extra["operation"]
        if parse_source is None and isinstance(extra.get("parse_source"), str):
            parse_source = extra["parse_source"]
        meta = trace_metadata(
            backend=backend,
            operation=operation,
            parse_source=parse_source,
            agent_caller=agent_caller,
            extra=extra,
        )
        trace_title = name or trace_name(backend, operation)
        trace_tag_list = tags or trace_tags(
            backend, operation, parse_source=parse_source, agent_caller=agent_caller
        )
        await self._enqueue_trace(
            trace_id,
            name=trace_title,
            tags=trace_tag_list,
            metadata=meta,
            output=sanitize_payload(output) if output is not None else None,
        )

    async def _enqueue(self, event: dict[str, Any]) -> None:
        global _trace_queue
        if _trace_queue is None:
            return
        try:
            _trace_queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("Langfuse queue full — dropping event")

    async def _send_batch(self, events: list[dict[str, Any]]) -> None:
        auth = self._auth_header()
        if not auth or not events:
            if self.enabled and events and not auth:
                logger.warning("Langfuse keys missing — dropping %s event(s)", len(events))
            return
        host = settings.LANGFUSE_HOST.rstrip("/")
        batch = [
            {
                "id": str(uuid.uuid4()),
                "type": e["type"],
                "timestamp": _now_iso(),
                "body": e["body"],
            }
            for e in events
        ]
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{host}/api/public/ingestion",
                    headers={
                        "Authorization": f"Basic {auth}",
                        "Content-Type": "application/json",
                    },
                    json={"batch": batch},
                )
            if resp.status_code not in (200, 207):
                logger.error(
                    "Langfuse ingestion failed [%s]: %s",
                    resp.status_code,
                    resp.text[:300],
                )
                return
            payload = resp.json()
            errors = payload.get("errors") or []
            if errors:
                logger.error("Langfuse ingestion batch errors: %s", errors[:3])
                return
            logger.debug(
                "Langfuse batch sent: %s event(s)",
                len(payload.get("successes") or []),
            )
        except Exception as exc:
            logger.error("Langfuse ingestion error: %s", exc)

    async def worker(self) -> None:
        buffer: list[dict[str, Any]] = []
        while True:
            try:
                event = await _trace_queue.get()
                buffer.append(event)
                if len(buffer) >= 5 or _trace_queue.empty():
                    await self._send_batch(buffer)
                    buffer.clear()
                _trace_queue.task_done()
            except asyncio.CancelledError:
                if buffer:
                    await self._send_batch(buffer)
                break
            except Exception as exc:
                logger.error("Tracer worker error: %s", exc)
                await asyncio.sleep(0.5)


tracer = ToolAgentTracer()


async def start_worker() -> asyncio.Task:
    global _worker_task, _trace_queue
    if not settings.LANGFUSE_ENABLED:
        return asyncio.create_task(asyncio.sleep(0))
    _trace_queue = asyncio.Queue(maxsize=500)
    _worker_task = asyncio.create_task(tracer.worker())
    return _worker_task


async def stop_worker() -> None:
    global _worker_task
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
