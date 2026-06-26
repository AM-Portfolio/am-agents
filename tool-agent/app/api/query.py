from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse

from app.config import settings
from app.models.intent import (
    ToolsExecuteRequest,
    ToolsPlanRequest,
    ToolsPlanResponse,
    ToolsQueryRequest,
    ToolsQueryResponse,
)
from app.runner import run_tools_execute, run_tools_plan, run_tools_query
from app.runner_stream import stream_tools_execute, stream_tools_plan, stream_tools_query

router = APIRouter()


def _agent_caller(x_agent_caller: str | None) -> str | None:
    return x_agent_caller.strip() if x_agent_caller else None


def _sse_response(gen) -> StreamingResponse:
    return StreamingResponse(
        gen,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/query", response_model=ToolsQueryResponse)
async def tools_query(
    body: ToolsQueryRequest,
    x_agent_caller: str | None = Header(default=None, alias="X-Agent-Caller"),
) -> ToolsQueryResponse:
    outcome = await run_tools_query(body, agent_caller=_agent_caller(x_agent_caller))
    if "error" in outcome:
        detail = outcome["error"]
        if outcome.get("intent"):
            detail = outcome
        raise HTTPException(status_code=outcome.get("status", 500), detail=detail)
    return outcome["response"]


@router.post("/query/stream")
async def tools_query_stream(
    body: ToolsQueryRequest,
    x_agent_caller: str | None = Header(default=None, alias="X-Agent-Caller"),
):
    if not settings.TOOL_AGENT_STREAMING_ENABLED:
        raise HTTPException(status_code=503, detail="Streaming disabled")
    return _sse_response(stream_tools_query(body, agent_caller=_agent_caller(x_agent_caller)))


@router.post("/plan", response_model=ToolsPlanResponse)
async def tools_plan(
    body: ToolsPlanRequest,
    x_agent_caller: str | None = Header(default=None, alias="X-Agent-Caller"),
) -> ToolsPlanResponse:
    outcome = await run_tools_plan(body, agent_caller=_agent_caller(x_agent_caller))
    if "error" in outcome:
        raise HTTPException(status_code=outcome.get("status", 500), detail=outcome["error"])
    return outcome["plan"]


@router.post("/plan/stream")
async def tools_plan_stream(
    body: ToolsPlanRequest,
    x_agent_caller: str | None = Header(default=None, alias="X-Agent-Caller"),
):
    if not settings.TOOL_AGENT_STREAMING_ENABLED:
        raise HTTPException(status_code=503, detail="Streaming disabled")
    return _sse_response(stream_tools_plan(body, agent_caller=_agent_caller(x_agent_caller)))


@router.post("/execute", response_model=ToolsQueryResponse)
async def tools_execute(
    body: ToolsExecuteRequest,
    x_agent_caller: str | None = Header(default=None, alias="X-Agent-Caller"),
) -> ToolsQueryResponse:
    outcome = await run_tools_execute(body, agent_caller=_agent_caller(x_agent_caller))
    if "error" in outcome:
        raise HTTPException(status_code=outcome.get("status", 500), detail=outcome["error"])
    return outcome["response"]


@router.post("/execute/stream")
async def tools_execute_stream(
    body: ToolsExecuteRequest,
    x_agent_caller: str | None = Header(default=None, alias="X-Agent-Caller"),
):
    if not settings.TOOL_AGENT_STREAMING_ENABLED:
        raise HTTPException(status_code=503, detail="Streaming disabled")
    return _sse_response(stream_tools_execute(body, agent_caller=_agent_caller(x_agent_caller)))
