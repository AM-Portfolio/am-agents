"""
Portfolio Analysis FastAPI Server
"""
import os
import sys
import uuid
import logging
from dotenv import load_dotenv

# Path setup: root is parent
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

# Force Portfolio Mode
os.environ["ENABLE_PORTFOLIO_ANALYSIS"] = "true"
os.environ["ENABLE_API_TESTING"] = "false"

load_dotenv(os.path.join(root_dir, ".env"), override=True)

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from shared.schemas.intent import ChatRequest, AiIntentResponse
from shared.session.store import session_store
from shared.middleware.logging_middleware import LoggingMiddleware
from shared.middleware.auth_middleware import (
    JwtUserMiddleware,
    cors_origins,
)
from shared.context.request_context import (
    auth_token_var,
    trace_id_var,
    session_id_var,
    user_id_var,
    request_id_var,
)
from shared.agents.finance_agent import finance_agent
from shared.core.config import settings

logger = logging.getLogger("am.fin.portfolio.api")

try:
    from shared.mcp_server.server import mcp_sse_app as _mcp_sse_app
except Exception as exc:  # noqa: BLE001 — local /ai/mcp is optional; chat uses Java MCP
    logger.warning("Local /ai/mcp disabled (mcp_server failed to load): %s", exc)
    _mcp_sse_app = None

from shared.observability.context import (
    ObservabilityContext,
    clear_obs_context,
    set_obs_context,
)
from shared.observability import tracer as lf

app = FastAPI(
    title="AM Portfolio Analysis API",
    description="AI-powered financial intelligence for portfolio management",
    version="1.0.0",
)

_origins = cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(JwtUserMiddleware)
app.add_middleware(LoggingMiddleware)
if _mcp_sse_app is not None:
    app.mount("/ai/mcp", _mcp_sse_app, name="mcp")
else:
    logger.info("Skipping /ai/mcp mount; chat uses AM_MCP_SERVER_URL=%s", settings.AM_MCP_SERVER_URL)

@app.get("/")
async def root():
    return {"message": "Portfolio Analysis API is running. Use /api/v1/ai/chat for agent interaction."}

@app.post("/api/v1/ai/chat", response_model=AiIntentResponse)
async def chat(request: ChatRequest, http_request: Request, response: Response) -> AiIntentResponse:
    # Session: body → X-Session-Id → new UUID
    header_session = (
        http_request.headers.get("x-session-id")
        or http_request.headers.get("X-Session-Id")
    )
    session_id = request.sessionId or header_session or str(uuid.uuid4())

    request_id = (
        http_request.headers.get("x-request-id")
        or http_request.headers.get("X-Request-Id")
        or request_id_var.get()
        or str(uuid.uuid4())
    )
    request_id_var.set(request_id)

    token_user = getattr(http_request.state, "token_user_id", None)
    user_id = request.userId
    if token_user:
        if user_id and user_id != token_user:
            logger.warning(
                "Body userId=%s differs from token subject=%s; using token",
                user_id,
                token_user,
            )
        user_id = token_user

    if not user_id or user_id.strip() in {"", "fin-agent"}:
        # Never use literal "fin-agent" as userId
        if user_id == "fin-agent":
            logger.warning("Rejected literal userId=fin-agent; using anonymous")
        user_id = user_id if user_id and user_id != "fin-agent" else "anonymous"

    # One Langfuse trace id per user turn
    turn_trace_id = lf.create_turn_trace_id(request_id)
    trace_id_var.set(turn_trace_id)
    session_id_var.set(session_id)
    user_id_var.set(user_id)
    auth_token_var.set(getattr(http_request.state, "auth_token", None) or "")

    obs = ObservabilityContext(
        session_id=session_id,
        user_id=user_id,
        trace_id=turn_trace_id,
        request_id=request_id,
        env=settings.LANGFUSE_ENV,
        tags=["fin-agent", f"env:{settings.LANGFUSE_ENV}", "surface:chat"],
        metadata={"requestId": request_id},
    )
    set_obs_context(obs)

    history = session_store.get(session_id)
    session_store.append(session_id, "user", request.message)

    error_text: str | None = None
    intent_response: AiIntentResponse | None = None
    try:
        with lf.turn_span(
            obs,
            name="fin.chat.turn",
            input={"message": request.message, "sessionId": session_id},
        ) as root_obs:
            try:
                intent_response = await finance_agent.run(
                    message=request.message,
                    history=history,
                    user_id=user_id,
                    session_id=session_id,
                    trace_id=turn_trace_id,
                )
                lf.end_turn(
                    root_obs,
                    output={
                        "artifactType": intent_response.artifactType,
                        "toolsUsed": intent_response.toolsUsed,
                        "message": intent_response.message[:500],
                    },
                )
            except Exception as e:
                error_text = str(e)
                lf.end_turn(root_obs, error=error_text)
                raise
    except Exception as e:
        logger.error(f"Agent failed: {e}")
        clear_obs_context()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            lf.flush()
        except Exception:  # noqa: BLE001
            pass
        clear_obs_context()

    assert intent_response is not None
    # Ensure response traceId is the Langfuse turn id
    intent_response.traceId = turn_trace_id
    intent_response.sessionId = session_id

    session_store.append(session_id, "assistant", intent_response.message)
    response.headers["X-Trace-Id"] = turn_trace_id
    response.headers["X-Request-Id"] = request_id
    response.headers["X-Session-Id"] = session_id
    return intent_response

@app.get("/health")
def health():
    return {"status": "ok", "module": "portfolio_analysis"}

@app.get("/ready")
def ready():
    return {
        "status": "ready",
        "data_plane": "am-mcp-server",
        "am_mcp_server_url": settings.AM_MCP_SERVER_URL,
        "data_fallback_rest": settings.DATA_FALLBACK_REST,
        "prompt_source": settings.PROMPT_SOURCE,
        "langfuse_enabled": settings.LANGFUSE_ENABLED,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8101)
