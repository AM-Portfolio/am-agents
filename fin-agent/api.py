"""
am-fin-agent FastAPI Server
Port: 8100

Endpoints:
  POST /v1/ai/chat       — main chat endpoint (returns AiIntentResponse)
  GET  /v1/ai/stream/{sessionId} — SSE status stream (future use)
  GET  /health               — health check
  GET  /ready                — readiness check (tools loaded?)
"""
import os
import sys
import uuid
import logging
import json
import asyncio
import httpx
import time
import traceback

# Load env FIRST before any local imports
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), override=True)
from datetime import datetime

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from shared.schemas.intent import ChatRequest, AiIntentResponse, WidgetId
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from shared.session.store import session_store
from shared.middleware.logging_middleware import LoggingMiddleware
from shared.context.request_context import user_id_var, session_id_var, trace_id_var
from shared.core.config import settings
from shared.agents.finance_agent import finance_agent
from shared.tools.registry import TOOL_REGISTRY
from shared.core.db import db_client

# ─── App Factory ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="AM Finance Agent API",
    description="AI-powered financial intelligence agent with multi-domain tool registry",
    version="2.0.0",
)

# Conditional Module Loading
if settings.ENABLE_API_TESTING:
    try:
        from am_fin_api_testing.routes import router as api_testing_router
        from am_fin_api_testing.routes import startup_background as api_testing_startup
        app.include_router(api_testing_router)
        logger.info("✅ API Testing router included.")
    except ImportError as e:
        logger.error(f"❌ Failed to include API Testing router: {e}")

# CORS — allow Dashboard and other local clients
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8100",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False, # Must be False if allow_origins is ["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)

# ─── Static Files & Redirects ────────────────────────────────────────────────

@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard")

# Mount dashboard.html as /dashboard
@app.get("/dashboard")
async def get_dashboard():
    from fastapi.responses import FileResponse
    import os
    _here = os.path.dirname(os.path.abspath(__file__))
    dashboard_path = os.path.join(_here, "dashboard.html")
    return FileResponse(dashboard_path)

# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.post("/v1/ai/chat", response_model=AiIntentResponse)
async def chat(request: ChatRequest) -> AiIntentResponse:
    """
    Main AI chat endpoint.
    Accepts a user message + userId, runs the FinanceAgent,
    and returns a structured AiIntentResponse for Flutter to render.
    """
    session_id = request.sessionId or str(uuid.uuid4())
    trace_id = trace_id_var.get() or str(uuid.uuid4())

    # 1. Load session history
    logger.info(f"RECEIVED CHAT REQUEST: {request.message} (User: {request.userId})")
    logger.info(f"Processing chat request for user {request.userId}")
    history = session_store.get(session_id)

    # 2. Save user message to session
    session_store.append(session_id, "user", request.message)

    # 3. Run the agent
    try:
        response = await finance_agent.run(
            message=request.message,
            history=history,
            user_id=request.userId,
            session_id=session_id,
            trace_id=trace_id,
        )
    except Exception as e:
        logger.error(f"Agent failed: {e}", extra={"trace_id": trace_id})
        raise HTTPException(status_code=500, detail=str(e))

    # 4. Save assistant response to session
    session_store.append(session_id, "assistant", response.message)

    return response


@app.get("/v1/ai/stream/{session_id}")
async def stream_status(session_id: str):
    """
    Server-Sent Events endpoint for live agent status updates.
    Flutter connects here to receive 'Thinking...' / 'Fetching data...' messages.
    (Scaffold: full event emission will be added in Phase H.4.)
    """
    async def event_generator():
        yield f"data: {json.dumps({'type': 'status', 'content': 'Connected to session ' + session_id})}\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/health")
def health():
    """Liveness probe."""
    return {"status": "ok", "service": "am-fin-agent", "port": 8080}


@app.get("/ready")
def ready():
    """Readiness probe — confirms tools loaded correctly."""
    tool_names = [t["function"]["name"] for t in TOOL_REGISTRY]
    if not tool_names:
        raise HTTPException(status_code=503, detail="Tool registry is empty — startup failed.")
    return {
        "status": "ready",
        "tools_registered": len(tool_names),
        "tools": tool_names,
    }

# ─── Startup Logic ────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    """Initialize enabled modules and build global tool index."""
    if settings.ENABLE_API_TESTING:
        asyncio.create_task(api_testing_startup())
    else:
        # If API testing is disabled, we still want to index other tools (portfolio, etc.)
        asyncio.create_task(_index_remaining_tools())

async def _index_remaining_tools():
    """Build ChromaDB vector index from all registered tools (fallback if meta-engine skipped)."""
    try:
        from shared.tools.tool_index import index_all_tools
        count = index_all_tools()
        logger.info(f"✅ Indexed {count} tools into ChromaDB.")
    except Exception as e:
        logger.warning(f"ChromaDB indexing skipped: {e}")


# ─── Dev entrypoint ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8080, reload=True)
