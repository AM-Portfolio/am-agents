"""
Portfolio Analysis FastAPI Server
"""
import os
import sys
import uuid
import logging
import json
import asyncio
from dotenv import load_dotenv

# Path setup: root is parent
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

# Force Portfolio Mode
os.environ["ENABLE_PORTFOLIO_ANALYSIS"] = "true"
os.environ["ENABLE_API_TESTING"] = "false"

load_dotenv(os.path.join(root_dir, ".env"), override=True)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from shared.schemas.intent import ChatRequest, AiIntentResponse
from shared.session.store import session_store
from shared.middleware.logging_middleware import LoggingMiddleware
from shared.context.request_context import trace_id_var
from shared.agents.finance_agent import finance_agent
from shared.tools.registry import TOOL_REGISTRY
from shared.streaming.events import error_event

logger = logging.getLogger("am.fin.portfolio.api")

app = FastAPI(
    title="AM Portfolio Analysis API",
    description="AI-powered financial intelligence for portfolio management",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)

@app.get("/")
async def root():
    return {"message": "Portfolio Analysis API is running. Use /api/v1/ai/chat for agent interaction."}

@app.post("/api/v1/ai/chat", response_model=AiIntentResponse)
async def chat(request: ChatRequest) -> AiIntentResponse:
    session_id = request.sessionId or str(uuid.uuid4())
    trace_id = trace_id_var.get() or str(uuid.uuid4())

    history = session_store.get_history(request.userId, session_id)
    session_store.append_turn(request.userId, session_id, "user", request.message)

    try:
        response = await finance_agent.run(
            message=request.message,
            history=history,
            user_id=request.userId,
            session_id=session_id,
            trace_id=trace_id,
        )
    except Exception as e:
        logger.error("Agent failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    session_store.append_turn(request.userId, session_id, "assistant", response.message)
    return response


@app.post("/api/v1/ai/chat/stream")
@app.get("/api/v1/ai/chat/stream")
async def chat_stream(
    request: ChatRequest | None = None,
    message: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
):
    msg = (request.message if request else message) or ""
    uid = (request.userId if request else user_id) or "anonymous"
    sid = (request.sessionId if request else session_id) or str(uuid.uuid4())
    tid = trace_id_var.get() or str(uuid.uuid4())

    if not msg:
        raise HTTPException(status_code=400, detail="Missing message parameter")

    history = session_store.get_history(uid, sid)
    session_store.append_turn(uid, sid, "user", msg)

    async def event_generator():
        try:
            async for sse_chunk in finance_agent.run_stream(
                message=msg,
                history=history,
                user_id=uid,
                session_id=sid,
                trace_id=tid,
            ):
                yield sse_chunk
        except Exception as exc:
            logger.error("Streaming error: %s", exc)
            yield error_event(str(exc), tid, sid).to_sse()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Trace-Id": tid,
            "X-Session-Id": sid,
        },
    )


@app.post("/api/v1/ai/feedback")
async def feedback(payload: dict):
    logger.info("Received user feedback: %s", payload)
    return {"status": "ok", "message": "Feedback recorded"}


@app.get("/health")
def health():
    return {"status": "ok", "module": "portfolio_analysis"}

@app.get("/ready")
def ready():
    tool_names = [t["function"]["name"] for t in TOOL_REGISTRY]
    return {
        "status": "ready",
        "tools_registered": len(tool_names),
        "tools": tool_names,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8101)

