from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from app.intent_schema import DbExecuteRequest, DbPlanRequest, DbPlanResponse, DbQueryRequest, DbQueryResponse
from app.runner import run_db_execute, run_db_plan, run_db_query

router = APIRouter()


def _agent_caller(x_agent_caller: str | None) -> str | None:
    return x_agent_caller.strip() if x_agent_caller else None


@router.post("/query", response_model=DbQueryResponse)
async def db_query(
    body: DbQueryRequest,
    x_agent_caller: str | None = Header(default=None, alias="X-Agent-Caller"),
) -> DbQueryResponse:
    outcome = await run_db_query(body, agent_caller=_agent_caller(x_agent_caller))
    if "error" in outcome:
        detail = outcome["error"]
        if outcome.get("intent"):
            detail = outcome
        raise HTTPException(status_code=outcome.get("status", 500), detail=detail)
    return outcome["response"]


@router.post("/plan", response_model=DbPlanResponse)
async def db_plan(
    body: DbPlanRequest,
    x_agent_caller: str | None = Header(default=None, alias="X-Agent-Caller"),
) -> DbPlanResponse:
    outcome = await run_db_plan(body, agent_caller=_agent_caller(x_agent_caller))
    if "error" in outcome:
        raise HTTPException(status_code=outcome.get("status", 500), detail=outcome["error"])
    return outcome["plan"]


@router.post("/execute", response_model=DbQueryResponse)
async def db_execute(
    body: DbExecuteRequest,
    x_agent_caller: str | None = Header(default=None, alias="X-Agent-Caller"),
) -> DbQueryResponse:
    outcome = await run_db_execute(body, agent_caller=_agent_caller(x_agent_caller))
    if "error" in outcome:
        raise HTTPException(status_code=outcome.get("status", 500), detail=outcome["error"])
    return outcome["response"]
