from __future__ import annotations

import uuid
import time
from fastapi import APIRouter, Header, HTTPException
from typing import cast

from app.models.intent import ReactRequest, ReactResponse
from app.react_graph import react_graph
from app.state import ReactAgentState

router = APIRouter()

def _agent_caller(x_agent_caller: str | None) -> str | None:
    return x_agent_caller.strip() if x_agent_caller else None

@router.post("/react", response_model=ReactResponse)
async def tools_react(
    body: ReactRequest,
    x_agent_caller: str | None = Header(default=None, alias="X-Agent-Caller"),
) -> ReactResponse:
    request_id = str(uuid.uuid4())
    
    initial_state: ReactAgentState = {
        "request": body,
        "request_id": request_id,
        "query": body.query,
        "history": [],
        "loop_count": 0,
        "agent_caller": _agent_caller(x_agent_caller),
    }

    try:
        final_state = await react_graph.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": request_id}}
        )
        
        final_state = cast(ReactAgentState, final_state)
        
        if final_state.get("error"):
            raise HTTPException(status_code=500, detail=final_state["error"])
            
        return ReactResponse(
            request_id=request_id,
            final_answer=final_state.get("final_answer", ""),
            history=final_state.get("history", [])
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ReAct loop failed: {e}")
