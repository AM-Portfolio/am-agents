import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.runner import execute_ui_test

logger = logging.getLogger(__name__)

router = APIRouter()

test_runs: Dict[str, Dict[str, Any]] = {}
_run_lock = asyncio.Lock()


class TestRunRequest(BaseModel):
    targetUrl: str = Field(..., description="Staging/Preprod application base URL")
    specification: Optional[str] = Field(default=None, description="Gherkin specs for target assertions")
    profile: str = Field(default="RELEASE_GATE", description="Run profile: AUTH_FLOW | RELEASE_GATE | SMOKE")
    commitSha: Optional[str] = Field(default=None, description="Git commit hash from code repository")
    branch: Optional[str] = Field(default="main", description="Source branch")
    callbackUrl: Optional[str] = Field(default=None, description="VCS system commit status endpoint")
    baselineMode: Optional[str] = Field(
        default=None,
        description="compare | seed | promote — Qdrant baseline lifecycle",
    )


class AuthTestRunRequest(BaseModel):
    targetUrl: Optional[str] = Field(
        default=None,
        description="Override URL; defaults to MODERN_UI_PORTFOLIO_URL or MODERN_UI_MAIN_URL",
    )
    uiMode: Optional[str] = Field(default=None, description="portfolio | main — sets AUTH_FLOW_* profile")
    commitSha: Optional[str] = Field(default=None)
    branch: Optional[str] = Field(default="main")
    baselineMode: Optional[str] = Field(
        default=None,
        description="compare | seed | promote — Qdrant baseline lifecycle",
    )


class TestRunResponse(BaseModel):
    testId: str
    status: str
    message: str


async def execute_agent_task(test_id: str, payload: Dict[str, Any]) -> None:
    async with _run_lock:
        await _execute_agent_task_inner(test_id, payload)


async def _execute_agent_task_inner(test_id: str, payload: Dict[str, Any]) -> None:
    logger.info(
        "Starting UI test run %s profile=%s target=%s",
        test_id,
        payload["profile"],
        payload["targetUrl"],
    )
    test_runs[test_id]["status"] = "RUNNING"

    result = await execute_ui_test(test_id, payload)
    test_runs[test_id].update(result)

    if result.get("status") == "COMPLETED":
        callback_url = payload.get("callbackUrl")
        if callback_url:
            await trigger_vcs_callback(
                callback_url,
                "success",
                f"UI Tests completed. Report: {result.get('report')}",
            )
        return

    callback_url = payload.get("callbackUrl")
    if callback_url:
        await trigger_vcs_callback(
            callback_url,
            "failure",
            f"UI Tests failed: {result.get('error')}",
        )


async def trigger_vcs_callback(url: str, state: str, description: str) -> None:
    logger.info("VCS callback %s → %s (%s)", url, state, description)


@router.post("/run", response_model=TestRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def run_test_suite(request: TestRunRequest, background_tasks: BackgroundTasks):
    test_id = str(uuid.uuid4())
    test_runs[test_id] = {"status": "QUEUED", "payload": request.model_dump()}
    background_tasks.add_task(execute_agent_task, test_id, request.model_dump())
    return TestRunResponse(
        testId=test_id,
        status="QUEUED",
        message=f"UI test queued (profile={request.profile}, LLM={settings.LLM_ROUTING}).",
    )


@router.post("/run/auth", response_model=TestRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def run_auth_flow_test(request: AuthTestRunRequest, background_tasks: BackgroundTasks):
    """Run the predefined am-modern-ui authentication flow (no LLM planner required)."""
    ui_mode = (request.uiMode or settings.UI_APP_MODE).lower()
    if ui_mode == "main":
        profile = "AUTH_FLOW_MAIN"
        target = request.targetUrl or settings.MODERN_UI_MAIN_URL
    else:
        profile = "AUTH_FLOW_PORTFOLIO"
        target = request.targetUrl or settings.MODERN_UI_PORTFOLIO_URL

    payload = {
        "targetUrl": target,
        "specification": "",
        "profile": profile,
        "commitSha": request.commitSha,
        "branch": request.branch,
        "callbackUrl": None,
        "baselineMode": request.baselineMode,
    }
    test_id = str(uuid.uuid4())
    test_runs[test_id] = {"status": "QUEUED", "payload": payload}
    background_tasks.add_task(execute_agent_task, test_id, payload)
    return TestRunResponse(
        testId=test_id,
        status="QUEUED",
        message=f"Auth flow test queued ({profile}) → {target}",
    )


@router.get("/status/{testId}")
async def get_test_status(testId: str):
    if testId not in test_runs:
        raise HTTPException(status_code=404, detail="Test execution ID not found")
    return test_runs[testId]


@router.get("/report/{testId}")
async def get_test_report_html(testId: str):
    report_path = None
    if testId in test_runs:
        report_path = test_runs[testId].get("report")
    if not report_path:
        report_path = str(Path(settings.REPORT_DIR) / f"{testId}.html")
    path = Path(report_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Report not ready yet")
    return FileResponse(path, media_type="text/html", filename=path.name)
