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
from app.schema.loader import get_schema_catalog
from tools._loader import get_enabled_tools, get_tools

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_registry()
    get_schema_catalog()
    get_tools()
    if settings.CATALOG_CACHE_WARM_ON_READY:
        from tools.kafka.topic_cache import refresh_topic_cache
        from tools.vault.path_cache import refresh_path_cache

        await refresh_path_cache()
        await refresh_topic_cache()
    await start_worker()
    logger.info(
        "tool-agent starting env=%s tools=%s mcp_enabled=%s prompt_source=%s",
        settings.APP_ENV,
        [t.name for t in get_enabled_tools()],
        settings.MCP_ENABLED,
        settings.PROMPT_SOURCE,
    )
    yield
    await stop_worker()


app = FastAPI(
    title="AM Tool Agent",
    description="Plugin-based natural-language interface to AM infra tools",
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

app.include_router(query_router, prefix="/api/v1/tools")


@app.get("/health")
async def health():
    enabled = get_enabled_tools()
    return {
        "status": "ok",
        "service": "tool-agent",
        "env": settings.APP_ENV,
        "discovered_tools": [t.name for t in get_tools()],
        "enabled_tools": [t.name for t in enabled],
        "entity_resolution": any(t.manifest.has_entities for t in enabled),
    }


@app.get("/ready")
async def ready():
    registry_ok = bool(get_registry().backends)
    llm = get_llm_client()
    llm_ok = await llm.health_check() if llm.available else False
    catalog: dict[str, str] = {}
    if settings.CATALOG_CACHE_WARM_ON_READY:
        from tools.kafka.topic_cache import catalog_source as kafka_catalog_source
        from tools.vault.path_cache import catalog_source as vault_catalog_source

        catalog = {"vault": vault_catalog_source(), "kafka": kafka_catalog_source()}
    return {
        "status": "ok" if registry_ok or not get_enabled_tools() else "degraded",
        "registry_loaded": registry_ok,
        "enabled_tools": [t.name for t in get_enabled_tools()],
        "llm_routing": settings.LLM_ROUTING,
        "llm_reachable": llm_ok,
        "mcp_enabled": settings.MCP_ENABLED,
        "prompt_source": settings.PROMPT_SOURCE,
        "langfuse_enabled": settings.LANGFUSE_ENABLED,
        "entity_resolution": any(t.manifest.has_entities for t in get_enabled_tools()),
        "catalog_cache": catalog,
    }
