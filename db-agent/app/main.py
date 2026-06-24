from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.query import router as query_router
from app.config import settings
from app.llm_client import get_llm_client
from app.observability.tracer import start_worker, stop_worker
from app.registry import get_registry
from app.schema_catalog import get_schema_catalog

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_registry()
    await start_worker()
    logger.info(
        "db-agent starting env=%s mcp_enabled=%s deployment=%s langfuse=%s",
        settings.APP_ENV,
        settings.MCP_ENABLED,
        settings.MCP_DEPLOYMENT_MODE,
        settings.LANGFUSE_ENABLED,
    )
    yield
    await stop_worker()


app = FastAPI(
    title="AM DB Agent",
    description="Natural-language interface to AM infra databases",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query_router, prefix="/api/v1/db")


@app.get("/health")
async def health():
    catalog = get_schema_catalog()
    return {
        "status": "ok",
        "service": "db-agent",
        "env": settings.APP_ENV,
        "schema_catalog": catalog.environment,
        "entity_resolution": True,
    }


@app.get("/ready")
async def ready():
    registry_ok = bool(get_registry()._registry.get("backends"))
    llm = get_llm_client()
    llm_ok = await llm.health_check() if llm.available else False
    return {
        "status": "ok" if registry_ok else "degraded",
        "registry_loaded": registry_ok,
        "llm_routing": settings.LLM_ROUTING,
        "llm_reachable": llm_ok,
        "mcp_enabled": settings.MCP_ENABLED,
        "deployment_mode": settings.MCP_DEPLOYMENT_MODE,
        "langfuse_enabled": settings.LANGFUSE_ENABLED,
        "schema_catalog": get_schema_catalog().environment,
        "entity_resolution": True,
    }
