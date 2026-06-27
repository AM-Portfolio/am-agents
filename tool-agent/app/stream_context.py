from __future__ import annotations

import contextvars
from collections.abc import Awaitable, Callable
from typing import Any

StreamEmitFn = Callable[[str, dict[str, Any]], Awaitable[None]]

_stream_emit: contextvars.ContextVar[StreamEmitFn | None] = contextvars.ContextVar(
    "stream_emit", default=None
)
_streaming_active: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "streaming_active", default=False
)


def set_stream_emit(fn: StreamEmitFn | None) -> None:
    _stream_emit.set(fn)


def get_stream_emit() -> StreamEmitFn | None:
    return _stream_emit.get()


def set_streaming_active(active: bool) -> None:
    _streaming_active.set(active)


def is_streaming_active() -> bool:
    return _streaming_active.get()


async def emit_stream(event: str, data: dict[str, Any]) -> None:
    fn = get_stream_emit()
    if fn:
        await fn(event, data)
