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
from fastapi.responses import RedirectResponse
from shared.schemas.intent import ChatRequest, AiIntentResponse
from shared.session.store import session_store
from shared.middleware.logging_middleware import LoggingMiddleware
from shared.context.request_context import trace_id_var
from shared.agents.finance_agent import finance_agent
from shared.tools.registry import TOOL_REGISTRY

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

    history = session_store.get(session_id)
    session_store.append(session_id, "user", request.message)

    try:
        response = await finance_agent.run(
            message=request.message,
            history=history,
            user_id=request.userId,
            session_id=session_id,
            trace_id=trace_id,
        )
    except Exception as e:
        logger.error(f"Agent failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    session_store.append(session_id, "assistant", response.message)
    return response

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
