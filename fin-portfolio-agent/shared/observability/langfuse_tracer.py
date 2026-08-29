"""Langfuse ingestion for fin-agent — trace, generation (with prompt link), spans."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from shared.core.config import settings

logger = logging.getLogger(__name__)

_trace_queue: asyncio.Queue[dict[str, Any]] | None = None
_worker_task: asyncio.Task | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _auth_header() -> str | None:
    pk = settings.LANGFUSE_PUBLIC_KEY
    sk = settings.LANGFUSE_SECRET_KEY
    if not pk or not sk:
        return None
    return base64.b64encode(f"{pk}:{sk}".encode()).decode()


def _truncate(value: Any, max_chars: int | None = None) -> Any:
    limit = max_chars or settings.LANGFUSE_TRACE_MAX_OUTPUT_CHARS
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + "...(truncated)"
    if isinstance(value, list):
        return [_truncate(v, limit) for v in value]
    if isinstance(value, dict):
        return {k: _truncate(v, limit) for k, v in value.items()}
    return value


def _omit_none(data: dict[str, Any]) -> dict[str, Any]:
    """Drop None values — Langfuse rejects nulls in metadata."""
    return {k: v for k, v in data.items() if v is not None}


def _apply_prompt_link(body: dict[str, Any]) -> None:
    """
    Langfuse requires promptName and promptVersion together, or neither.
    Keep name/label in metadata when version is unknown.
    """
    version_raw = (settings.LANGFUSE_PROMPT_VERSION or "").strip()
    if not version_raw:
        return
    try:
        body["promptName"] = settings.LANGFUSE_PROMPT_NAME
        body["promptVersion"] = int(version_raw)
    except ValueError:
        logger.warning(
            "LANGFUSE_PROMPT_VERSION=%r is not an integer — omitting prompt link",
            version_raw,
        )


def serialize_chat_messages(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Full LLM payload for Langfuse generation input (system prompt included)."""
    rows: list[dict[str, Any]] = []
    for msg in messages:
        row: dict[str, Any] = {
            "role": msg.get("role"),
            "content": msg.get("content") or "",
        }
        if msg.get("tool_calls"):
            row["tool_calls"] = msg["tool_calls"]
        if msg.get("name"):
            row["name"] = msg["name"]
        if msg.get("tool_call_id"):
            row["tool_call_id"] = msg["tool_call_id"]
        rows.append(row)

    meta: dict[str, Any] = {"source": "fin-agent"}
    if tools:
        meta["tool_names"] = [
            t.get("function", {}).get("name")
            for t in tools
            if t.get("function", {}).get("name")
        ]
    return rows, meta


def serialize_llm_output(response: Any) -> str:
    if isinstance(response, dict):
        if response.get("tool_calls"):
            return json.dumps(
                {
                    "content": response.get("content") or "",
                    "tool_calls": response["tool_calls"],
                },
                default=str,
            )
        if response.get("content") is not None:
            return str(response.get("content") or "")
        return json.dumps(response, default=str)
    return str(response)


class FinLangfuseTracer:
    def __init__(self) -> None:
        self.enabled = settings.LANGFUSE_ENABLED

    async def start_chat_trace(
        self,
        trace_id: str,
        *,
        user_id: str,
        session_id: str,
        user_message: str,
        system_prompt: str,
    ) -> None:
        if not self.enabled:
            return
        await self._enqueue(
            {
                "type": "trace-create",
                "body": {
                    "id": trace_id,
                    "name": "fin-agent.chat",
                    "userId": user_id,
                    "sessionId": session_id,
                    "tags": ["fin-agent", "chat", settings.AM_AGENT_ENV],
                    "metadata": _omit_none(
                        {
                            "source": "fin-agent",
                            "prompt_name": settings.LANGFUSE_PROMPT_NAME,
                            "prompt_label": settings.LANGFUSE_PROMPT_LABEL,
                        }
                    ),
                    "input": _truncate(
                        {
                            "system_prompt": system_prompt,
                            "user_message": user_message,
                        }
                    ),
                },
            }
        )

    async def end_chat_trace(
        self,
        trace_id: str,
        *,
        user_id: str,
        session_id: str,
        answer: str,
        tools_called: list[str],
        widget_id: str | None = None,
        error: str | None = None,
    ) -> None:
        if not self.enabled:
            return
        body: dict[str, Any] = {
            "id": trace_id,
            "name": "fin-agent.chat",
            "userId": user_id,
            "sessionId": session_id,
            "tags": ["fin-agent", "chat", settings.AM_AGENT_ENV],
            "metadata": _omit_none(
                {
                    "source": "fin-agent",
                    "tools_called": tools_called,
                    "widget_id": widget_id,
                    "error": error,
                }
            ),
            "output": _truncate(answer),
        }
        await self._enqueue({"type": "trace-create", "body": body})

    async def record_generation(
        self,
        trace_id: str,
        *,
        name: str,
        model: str,
        messages: list[dict[str, Any]],
        response: Any,
        tools: list[dict[str, Any]] | None = None,
        usage: dict[str, Any] | None = None,
        error: str | None = None,
        tier: str | None = None,
    ) -> None:
        if not self.enabled:
            return
        generation_id = str(uuid.uuid4())
        now = _now_iso()
        input_rows, tool_meta = serialize_chat_messages(messages, tools=tools)
        meta = _omit_none(
            {
                "source": "fin-agent",
                "tier": tier,
                "prompt_name": settings.LANGFUSE_PROMPT_NAME,
                "prompt_label": settings.LANGFUSE_PROMPT_LABEL,
                "tool_names": tool_meta.get("tool_names"),
            }
        )

        body: dict[str, Any] = {
            "id": generation_id,
            "traceId": trace_id,
            "name": name,
            "model": model,
            "startTime": now,
            "endTime": now,
            "input": _truncate(input_rows),
            "output": _truncate(error or serialize_llm_output(response)),
            "metadata": meta,
        }
        _apply_prompt_link(body)
        if error:
            body["level"] = "ERROR"
            body["statusMessage"] = error
        if usage:
            body["usageDetails"] = {
                "input": int(usage.get("prompt_tokens") or 0),
                "output": int(usage.get("completion_tokens") or 0),
                "total": int(usage.get("total_tokens") or 0),
            }

        await self._enqueue({"type": "generation-create", "body": body})

    async def record_span(
        self,
        trace_id: str,
        name: str,
        *,
        input_data: Any = None,
        output_data: Any = None,
        metadata: dict[str, Any] | None = None,
        level: str = "DEFAULT",
    ) -> None:
        if not self.enabled:
            return
        now = _now_iso()
        span_body: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "traceId": trace_id,
            "name": name,
            "startTime": now,
            "endTime": now,
            "metadata": _omit_none({"source": "fin-agent", **(metadata or {})}),
            "level": level,
        }
        if input_data is not None:
            span_body["input"] = _truncate(input_data)
        if output_data is not None:
            span_body["output"] = _truncate(output_data)
        await self._enqueue(
            {
                "type": "span-create",
                "body": span_body,
            }
        )

    async def _enqueue(self, event: dict[str, Any]) -> None:
        global _trace_queue
        if _trace_queue is None:
            logger.warning(
                "Langfuse queue not started — dropping event type=%s (call start_langfuse_worker)",
                event.get("type"),
            )
            return
        try:
            _trace_queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.error("Langfuse queue full — dropping event type=%s", event.get("type"))

    async def _send_batch(self, events: list[dict[str, Any]]) -> None:
        auth = _auth_header()
        host = (settings.LANGFUSE_HOST or "").rstrip("/")
        if not auth or not host:
            logger.warning(
                "Langfuse keys/host missing — dropped %s event(s) (enabled=%s)",
                len(events),
                self.enabled,
            )
            return

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
            async with httpx.AsyncClient(timeout=15.0) as client:
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
                    resp.text[:400],
                )
                return
            payload = resp.json()
            errors = payload.get("errors") or []
            if errors:
                logger.error("Langfuse ingestion errors: %s", errors[:3])
                return
            logger.debug(
                "Langfuse batch ok: %s event(s)",
                len(payload.get("successes") or []),
            )
            logger.info(
                "Langfuse batch ingested: %s event(s) trace_ids=%s",
                len(payload.get("successes") or batch),
                [e["body"].get("traceId") or e["body"].get("id") for e in batch[:3]],
            )
        except Exception as exc:
            logger.error("Langfuse ingestion exception: %s", exc)

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
                logger.error("Langfuse worker error: %s", exc)
                await asyncio.sleep(0.5)

    async def flush(self) -> None:
        """Drain pending events (best-effort, e.g. end of request)."""
        global _trace_queue
        if _trace_queue is None:
            return
        pending: list[dict[str, Any]] = []
        while not _trace_queue.empty():
            try:
                pending.append(_trace_queue.get_nowait())
                _trace_queue.task_done()
            except asyncio.QueueEmpty:
                break
        if pending:
            await self._send_batch(pending)


fin_tracer = FinLangfuseTracer()


async def start_langfuse_worker() -> asyncio.Task:
    global _worker_task, _trace_queue
    if not settings.LANGFUSE_ENABLED:
        logger.info("Langfuse disabled — worker not started")
        return asyncio.create_task(asyncio.sleep(0))
    _trace_queue = asyncio.Queue(maxsize=500)
    _worker_task = asyncio.create_task(fin_tracer.worker())
    logger.info(
        "Langfuse worker started host=%s prompt=%s label=%s keys=%s",
        settings.LANGFUSE_HOST,
        settings.LANGFUSE_PROMPT_NAME,
        settings.LANGFUSE_PROMPT_LABEL,
        "ok" if _auth_header() else "MISSING",
    )
    return _worker_task


async def stop_langfuse_worker() -> None:
    global _worker_task
    if _worker_task and not _worker_task.done():
        await fin_tracer.flush()
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
