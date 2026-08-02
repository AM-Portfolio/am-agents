"""
Langfuse official SDK tracer for fin-portfolio-agent.

Fail-open: missing SDK / keys / network never breaks chat.
One sessionId per conversation; one traceId per user turn; nested spans.

Supports Langfuse Python SDK v3 (start_as_current_observation) with a
best-effort v2 fallback (trace/span/generation methods).
"""

from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager
from typing import Any, Generator, Optional

from shared.core.config import settings
from shared.observability.context import ObservabilityContext, get_obs_context
from shared.observability.sanitize import sanitize_payload

logger = logging.getLogger(__name__)

_client: Any = None
_client_checked = False
# v2 fallback: map trace_id -> root trace object
_v2_traces: dict[str, Any] = {}


def _env_tag() -> str:
    return f"env:{settings.LANGFUSE_ENV}"


def _get_client() -> Any:
    """Lazy Langfuse client; returns None when disabled or unavailable."""
    global _client, _client_checked
    if _client_checked:
        return _client
    _client_checked = True
    if not settings.LANGFUSE_ENABLED:
        return None
    if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        logger.warning("LANGFUSE_ENABLED but public/secret keys missing — tracing disabled")
        return None
    try:
        from langfuse import Langfuse

        kwargs: dict[str, Any] = {
            "public_key": settings.LANGFUSE_PUBLIC_KEY,
            "secret_key": settings.LANGFUSE_SECRET_KEY,
            "host": settings.LANGFUSE_HOST,
        }
        try:
            _client = Langfuse(**kwargs)
        except TypeError:
            # Older clients may use base_url
            kwargs.pop("host", None)
            kwargs["base_url"] = settings.LANGFUSE_HOST
            _client = Langfuse(**kwargs)
        return _client
    except Exception as exc:  # noqa: BLE001
        logger.warning("Langfuse SDK init failed (fail-open): %s", exc)
        _client = None
        return None


def create_turn_trace_id(request_id: str | None = None) -> str:
    """Prefer Langfuse create_trace_id; fall back to UUID hex."""
    client = _get_client()
    seed = request_id or str(uuid.uuid4())
    if client is not None and hasattr(client, "create_trace_id"):
        try:
            return client.create_trace_id(seed=seed)
        except Exception:  # noqa: BLE001
            pass
    return uuid.uuid4().hex


def flush() -> None:
    client = _get_client()
    if client is None:
        return
    try:
        client.flush()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Langfuse flush failed: %s", exc)


def _strip_secrets(meta: dict[str, Any]) -> dict[str, Any]:
    out = dict(meta)
    for banned in ("authorization", "token", "api_key", "secret", "password"):
        out.pop(banned, None)
    return out


@contextmanager
def turn_span(
    ctx: ObservabilityContext,
    *,
    name: str = "fin.chat.turn",
    input: Any = None,
) -> Generator[Any, None, None]:
    """Root span for one user turn. Yields observation or None (fail-open)."""
    client = _get_client()
    if client is None:
        yield None
        return

    tags = list(
        dict.fromkeys(
            [
                "fin-agent",
                "surface:chat",
                _env_tag(),
                *ctx.tags,
            ]
        )
    )
    meta = _strip_secrets(
        {
            "requestId": ctx.request_id,
            "source": "fin-agent",
            **(ctx.metadata or {}),
        }
    )
    safe_input = sanitize_payload(input) if input is not None else None

    # ── SDK v3 path ──────────────────────────────────────────────────────────
    if hasattr(client, "start_as_current_observation"):
        try:
            from langfuse import propagate_attributes

            with client.start_as_current_observation(
                as_type="span",
                name=name,
                input=safe_input,
                metadata=meta,
                trace_context={"trace_id": ctx.trace_id},
            ) as obs:
                try:
                    with propagate_attributes(
                        user_id=ctx.user_id,
                        session_id=ctx.session_id,
                        metadata=meta,
                        tags=tags,
                        trace_name=name,
                    ):
                        yield obs
                except TypeError:
                    with propagate_attributes(
                        user_id=ctx.user_id,
                        session_id=ctx.session_id,
                        metadata=meta,
                    ):
                        yield obs
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("Langfuse v3 turn_span failed, trying v2: %s", exc)

    # ── SDK v2 fallback ──────────────────────────────────────────────────────
    try:
        trace = client.trace(
            id=ctx.trace_id,
            name=name,
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            tags=tags,
            metadata=meta,
            input=safe_input,
        )
        _v2_traces[ctx.trace_id] = trace
        span = trace.span(name=name, input=safe_input, metadata=meta)
        yield span
        try:
            span.end()
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("Langfuse turn_span failed (fail-open): %s", exc)
        yield None


def end_turn(obs: Any, *, output: Any = None, error: str | None = None) -> None:
    if obs is None:
        return
    try:
        payload: dict[str, Any] = {}
        if output is not None:
            payload["output"] = sanitize_payload(output)
        if error:
            payload["level"] = "ERROR"
            payload["status_message"] = error[:500]
            payload["output"] = sanitize_payload({"error": error})
        if hasattr(obs, "update") and payload:
            try:
                obs.update(**payload)
                return
            except TypeError:
                pass
        # v2 span may use end(output=...)
        if hasattr(obs, "end"):
            obs.end(output=payload.get("output"))
        ctx = get_obs_context()
        if ctx and ctx.trace_id in _v2_traces:
            try:
                _v2_traces[ctx.trace_id].update(output=payload.get("output"))
            except Exception:  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001
        logger.debug("Langfuse end_turn update failed: %s", exc)


@contextmanager
def span(
    name: str,
    *,
    input: Any = None,
    metadata: dict[str, Any] | None = None,
) -> Generator[Any, None, None]:
    client = _get_client()
    ctx = get_obs_context()
    if client is None:
        yield None
        return
    meta = _strip_secrets({"source": "fin-agent", **(metadata or {})})
    if ctx:
        meta.setdefault("requestId", ctx.request_id)
    safe_input = sanitize_payload(input) if input is not None else None

    if hasattr(client, "start_as_current_observation"):
        try:
            with client.start_as_current_observation(
                as_type="span",
                name=name,
                input=safe_input,
                metadata=meta,
            ) as obs:
                yield obs
            return
        except Exception as exc:  # noqa: BLE001
            logger.debug("Langfuse v3 span %s failed: %s", name, exc)

    try:
        parent = _v2_traces.get(ctx.trace_id) if ctx else None
        if parent is not None:
            obs = parent.span(name=name, input=safe_input, metadata=meta)
            yield obs
            try:
                obs.end()
            except Exception:  # noqa: BLE001
                pass
            return
    except Exception as exc:  # noqa: BLE001
        logger.debug("Langfuse span %s failed (fail-open): %s", name, exc)
    yield None


def end_span(obs: Any, *, output: Any = None, error: str | None = None) -> None:
    if obs is None:
        return
    try:
        payload: dict[str, Any] = {}
        if output is not None:
            payload["output"] = sanitize_payload(output)
        if error:
            payload["level"] = "ERROR"
            payload["status_message"] = str(error)[:500]
        if hasattr(obs, "update") and payload:
            try:
                obs.update(**payload)
                return
            except TypeError:
                pass
        if hasattr(obs, "end"):
            obs.end(output=payload.get("output"))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Langfuse end_span failed: %s", exc)


@contextmanager
def generation(
    name: str,
    *,
    model: str,
    input: Any = None,
    metadata: dict[str, Any] | None = None,
) -> Generator[Any, None, None]:
    client = _get_client()
    ctx = get_obs_context()
    if client is None:
        yield None
        return
    meta: dict[str, Any] = _strip_secrets({"source": "fin-agent", **(metadata or {})})
    if ctx:
        meta.setdefault("requestId", ctx.request_id)
        if ctx.prompt_name:
            meta.setdefault("prompt_name", ctx.prompt_name)
        if ctx.prompt_version:
            meta.setdefault("prompt_version", ctx.prompt_version)
        if ctx.prompt_source:
            meta.setdefault("prompt_source", ctx.prompt_source)
    safe_input = sanitize_payload(input) if input is not None else None

    if hasattr(client, "start_as_current_observation"):
        try:
            with client.start_as_current_observation(
                as_type="generation",
                name=name,
                model=model,
                input=safe_input,
                metadata=meta,
            ) as obs:
                yield obs
            return
        except Exception as exc:  # noqa: BLE001
            logger.debug("Langfuse v3 generation %s failed: %s", name, exc)

    try:
        parent = _v2_traces.get(ctx.trace_id) if ctx else None
        if parent is not None:
            obs = parent.generation(
                name=name, model=model, input=safe_input, metadata=meta
            )
            yield obs
            try:
                obs.end()
            except Exception:  # noqa: BLE001
                pass
            return
    except Exception as exc:  # noqa: BLE001
        logger.debug("Langfuse generation %s failed (fail-open): %s", name, exc)
    yield None


def end_generation(
    obs: Any,
    *,
    output: Any = None,
    usage: dict[str, int] | None = None,
    error: str | None = None,
    prompt_obj: Any = None,
) -> None:
    if obs is None:
        return
    try:
        payload: dict[str, Any] = {}
        if output is not None:
            payload["output"] = sanitize_payload(output)
        if error:
            payload["level"] = "ERROR"
            payload["status_message"] = str(error)[:500]
        if usage:
            usage_details = {
                "input": usage.get("prompt_tokens", 0),
                "output": usage.get("completion_tokens", 0),
                "total": usage.get("total_tokens", 0),
            }
            payload["usage_details"] = usage_details
        if prompt_obj is not None and hasattr(obs, "update"):
            try:
                obs.update(prompt=prompt_obj, **{k: v for k, v in payload.items()})
                return
            except TypeError:
                pass
        if hasattr(obs, "update") and payload:
            try:
                obs.update(**payload)
                return
            except TypeError:
                # v2 may prefer usage= instead of usage_details
                alt = {k: v for k, v in payload.items() if k != "usage_details"}
                if usage:
                    alt["usage"] = usage
                try:
                    obs.update(**alt)
                    return
                except Exception:  # noqa: BLE001
                    pass
        if hasattr(obs, "end"):
            obs.end(output=payload.get("output"))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Langfuse end_generation failed: %s", exc)
