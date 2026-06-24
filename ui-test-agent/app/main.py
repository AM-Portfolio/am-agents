import logging
from contextlib import asynccontextmanager
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.api.design_baselines import router as design_baselines_router
from app.api.test_runner import router as test_runner_router

logging.basicConfig(
    level=logging.getLevelName(settings.LOG_LEVEL),
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s' if settings.LOG_FORMAT == 'text' else '{"time":"%(asctime)s", "level":"%(levelname)s", "name":"%(name)s", "message":"%(message)s"}',
)
logger = logging.getLogger("am-ui-test-agent")

scheduler = BackgroundScheduler(timezone=ZoneInfo(settings.TZ))

def nightly_regression_job():
    logger.info("Executing scheduled Nightly Regression job at 2:00 AM...")
    # Select active test suites and execute regression runs
    pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.llm_routing == "direct":
        logger.info(
            "LLM routing=direct → %s (planner=%s vision=%s)",
            settings.LITELLM_BASE_URL,
            settings.LLM_PLANNER_MODEL,
            settings.LLM_VISION_MODEL,
        )
    else:
        logger.info(
            "LLM routing=gateway → %s → LiteLLM %s (planner=%s vision=%s)",
            settings.MCP_GATEWAY_BASE_URL,
            settings.LITELLM_BASE_URL,
            settings.LLM_PLANNER_MODEL,
            settings.LLM_VISION_MODEL,
        )
    logger.info("Starting scheduled tasks...")
    # Run at 2:00 AM daily
    scheduler.add_job(nightly_regression_job, "cron", hour=2, minute=0)
    scheduler.start()
    yield
    # Shutdown: Stop Scheduler
    logger.info("Shutting down scheduled tasks...")
    scheduler.shutdown()

app = FastAPI(
    title="AM UI Test Agent",
    description="Autonomous testing engine running Playwright & Qwen2.5-VL",
    version="2.0.0",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(test_runner_router, prefix="/api/v1/test")
app.include_router(design_baselines_router, prefix="/api/v1/design")

@app.get("/health")
async def health():
    return {"status": "ok", "service": "am-ui-test-agent"}
