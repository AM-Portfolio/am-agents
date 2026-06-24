from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from app.models.intent import ToolsExecuteRequest, ToolsPlanRequest, ToolsPlanResponse, ToolsQueryRequest, ToolsQueryResponse
from app.runner import run_tools_execute, run_tools_plan, run_tools_query

router = APIRouter()


def _agent_caller(x_agent_caller: str | None) -> str | None:
    return x_agent_caller.strip() if x_agent_caller else None


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


@router.post("/plan", response_model=ToolsPlanResponse)
async def tools_plan(
    body: ToolsPlanRequest,
    x_agent_caller: str | None = Header(default=None, alias="X-Agent-Caller"),
) -> ToolsPlanResponse:
    outcome = await run_tools_plan(body, agent_caller=_agent_caller(x_agent_caller))
    if "error" in outcome:
        raise HTTPException(status_code=outcome.get("status", 500), detail=outcome["error"])
    return outcome["plan"]


@router.post("/execute", response_model=ToolsQueryResponse)
async def tools_execute(
    body: ToolsExecuteRequest,
    x_agent_caller: str | None = Header(default=None, alias="X-Agent-Caller"),
) -> ToolsQueryResponse:
    outcome = await run_tools_execute(body, agent_caller=_agent_caller(x_agent_caller))
    if "error" in outcome:
        raise HTTPException(status_code=outcome.get("status", 500), detail=outcome["error"])
    return outcome["response"]
