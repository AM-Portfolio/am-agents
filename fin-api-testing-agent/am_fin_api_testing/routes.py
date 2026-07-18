import os
import json
import logging
import asyncio
import httpx
import time
import traceback
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .core.meta_engine import meta_engine
from shared.core.db import db_client
from shared.agents.finance_agent import finance_agent
from shared.tools.registry import TOOL_REGISTRY

logger = logging.getLogger("am.fin.api_testing.routes")

router = APIRouter(prefix="/api/v1/meta", tags=["API Testing"])

# ─── Global State for Dashboard ──────────────────────────────────────────────

class DashboardLogger:
    def __init__(self):
        self.queues = {} # sessionId -> asyncio.Queue

    def get_queue(self, session_id):
        if session_id not in self.queues:
            self.queues[session_id] = asyncio.Queue()
        return self.queues[session_id]

    async def log(self, session_id, log_type, content):
        queue = self.get_queue(session_id)
        await queue.put({"time": time.strftime("%H:%M:%S"), "type": log_type, "content": content})

dashboard_logger = DashboardLogger()

# ─── Config & Service Discovery ─────────────────────────────────────────────

def load_services_config() -> Dict[str, Dict[str, str]]:
    config = {
        "Auth Tokens": {"url": "http://localhost:8001", "spec": "http://localhost:8001/auth/token/v1/openapi.json"},
        "User Management": {"url": "http://localhost:8002", "spec": "http://localhost:8002/openapi.json"},
        "Market Data": {"url": "http://localhost:8092", "spec": "http://localhost:8092/v3/api-docs"},
        "Trade Service": {"url": "http://localhost:8040", "spec": "http://localhost:8040/v3/api-docs"},
        "Analysis Service": {"url": "http://localhost:8010", "spec": "http://localhost:8010/openapi.json"},
        "Market Data Parser": {"url": "http://localhost:8022", "spec": "http://localhost:8022/openapi.json"},
        "Document Processor": {"url": "http://localhost:8081", "spec": "http://localhost:8081/v3/api-docs"},
        "Email Extractor": {"url": "http://localhost:8080", "spec": "http://localhost:8080/api/v1/health"},
    }

    json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "services.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r") as f:
                external_config = json.load(f)
                if isinstance(external_config, dict):
                    config.update(external_config)
                    logger.info(f"Loaded {len(external_config)} services from services.json")
        except Exception as e:
            logger.error(f"Failed to load services.json: {e}")

    for i in range(1, 11):
        name = os.getenv(f"SERVICE_{i}_NAME")
        url = os.getenv(f"SERVICE_{i}_URL")
        spec = os.getenv(f"SERVICE_{i}_SPEC")
        if name and url:
            config[name] = {"url": url, "spec": spec or f"{url}/openapi.json"}
            logger.info(f"Loaded service '{name}' from environment variables")

    return config

SERVICES = load_services_config()
CACHE_FILE = "/tmp/discovery_cache.json"

async def load_service_specs() -> Dict[str, Any]:
    logger.info("Initializing MetaEngine for Dashboard Support (Background)...")
    service_specs = {}
    loaded_cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                loaded_cache = json.load(f)
                for name, data in loaded_cache.items():
                    spec_json = data["json"]
                    url = data["url"]
                    meta_engine.add_registry_json(spec_json, url)
                    service_specs[name] = spec_json
            logger.info(f"Loaded {len(loaded_cache)} services from local cache.")
        except Exception as e:
            logger.warning(f"Failed to load discovery cache: {e}")

    updated_cache = {**loaded_cache}
    for name, info in SERVICES.items():
        try:
            logger.info(f"Attempting to refresh {name} spec from {info['spec']}...")
            async with httpx.AsyncClient(timeout=45.0) as client:
                resp = await client.get(info["spec"])
                if resp.status_code == 200:
                    if name != "Email Extractor":
                        spec_json = resp.json()
                    else:
                        spec_json = {
                            "openapi": "3.0.0",
                            "info": {"title": "Email Extractor API", "version": "1.0.0"},
                            "paths": {
                                "/api/v1/health": {"get": {"operationId": "email_extractor_health", "summary": "Health Check"}},
                                "/api/v1/extract/gmail/groww": {"get": {"operationId": "extract_groww_gmail", "summary": "Extract Groww from Gmail"}},
                                "/api/v1/extract/gmail/zerodha": {"get": {"operationId": "extract_zerodha_gmail", "summary": "Extract Zerodha from Gmail"}},
                                "/api/v1/extract/upload/groww": {"post": {"operationId": "upload_groww", "summary": "Upload Groww Statement"}}
                            }
                        }
                    
                    meta_engine.add_registry_json(spec_json, info["url"])
                    updated_cache[name] = {"url": info["url"], "json": spec_json}
                    service_specs[name] = spec_json
                    logger.info(f"✅ Successfully loaded/refreshed {name} spec. Endpoints: {len(spec_json.get('paths', {}))}")
                else:
                    logger.warning(f"❌ Failed to refresh {name} spec: HTTP {resp.status_code}")
        except Exception as e:
            logger.warning(f"❌ Failed to refresh {name} spec ({type(e).__name__}): {e}")
    
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(updated_cache, f)
    except Exception as e:
        logger.error(f"Failed to save discovery cache: {e}")

    logger.info("Service discovery refresh complete.")
    return service_specs

async def startup_background():
    await meta_engine.refresh_all_specs(dashboard_logger)
    logger.info("Service discovery refresh complete.")

# ─── Schemas ──────────────────────────────────────────────────────────────────

class BatchRequest(BaseModel):
    service: str
    sessionId: str

class AnalyzeRequest(BaseModel):
    operation_id: str
    result: Dict[str, Any]
    user_context: Optional[str] = None
    history: Optional[List[Dict[str, str]]] = []

# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/config")
async def get_config():
    return meta_engine.load_services()

@router.post("/config")
async def update_config(services: List[Dict[str, str]]):
    meta_engine.save_services(services)
    return {"status": "success", "message": "Configuration updated and discovery restarted"}

@router.get("/services")
async def get_services():
    results = []
    services = meta_engine.load_services()
    for s in services:
        status = await meta_engine.check_service_health(s)
        base_url = s["url"].rstrip("/")
        ops = [api for api in meta_engine.apis if meta_engine.base_url_map.get(api.get("operationId")) == base_url]
        results.append({
            "name": s["name"],
            "url": s["url"],
            "status": status,
            "endpoints": len(ops)
        })
    return results

@router.get("/services/{service_name}/apis")
async def get_service_apis(service_name: str):
    services = meta_engine.load_services()
    service_info = next((s for s in services if s["name"] == service_name), None)
    if not service_info:
        raise HTTPException(status_code=404, detail="Service not found")
    
    base_url = service_info["url"].rstrip("/")
    service_apis = []
    
    for api in meta_engine.apis:
        op_id = api.get("operationId")
        if meta_engine.base_url_map.get(op_id) == base_url:
            service_apis.append({
                "operationId": op_id,
                "summary": api.get("summary", "No summary"),
                "path": api.get("path"),
                "method": api.get("method"),
                "description": api.get("description", "")
            })
            
    return service_apis

@router.get("/test/template/{operation_id}")
async def get_api_template(operation_id: str):
    try:
        template = await meta_engine.generate_payload_template(operation_id)
        return template
    except Exception as e:
        logger.error(f"Template generation failed: {e}")
        return {"error": str(e)}

@router.post("/analyze/stream")
async def analyze_failure_stream(request: AnalyzeRequest):
    logger.info(f"Streaming failure analysis for {request.operation_id}")
    api_details = meta_engine.get_api_details(request.operation_id) or {}
    
    prompt = f"""
    [SYSTEM CONTEXT]
    You are an autonomous API Diagnostic Agent. 
    Analyze the following interaction and address the user's intent directly.
    
    [API SPECIFICATION]
    {json.dumps(api_details, indent=2)}
    
    [TEST EXECUTION DATA]
    Status Code: {request.result.get('code', 'unknown')}
    {json.dumps(request.result, indent=2)}
    
    [USER INTENT / CONTEXT]
    {request.user_context or 'Initial exploration of the test result.'}
    
    [INSTRUCTIONS]
    - Reasoning: Identify whether this was a success, a logical failure, or a schema violation.
    - Response: Be concise. If the user asked a question, answer it using the available data. 
    - Formatting: Use markdown. Break complex data into readable bullet points.
    - Tone: Senior Engineer / Peer debugger.
    """
    
    async def event_generator():
        try:
            async for event_json in finance_agent.run_stream(
                message=prompt,
                history=request.history or [],
                user_id="system_diagnostic",
                session_id=f"analyze_{request.operation_id}",
                trace_id=f"trace_{request.operation_id}_{datetime.utcnow().timestamp()}"
            ):
                yield f"data: {event_json}\n\n"
        except Exception as e:
            logger.error(f"Streaming analysis failed: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.post("/analyze")
async def analyze_failure(request: AnalyzeRequest):
    logger.info(f"Analyzing failure for {request.operation_id} (non-streaming)")
    prompt = f"The test for API operation '{request.operation_id}' failed. Result: {json.dumps(request.result)}"
    try:
        response = await finance_agent.run(
            message=prompt,
            history=[],
            user_id="system_diagnostic",
            session_id=f"analyze_{request.operation_id}",
            trace_id=f"trace_{request.operation_id}_{datetime.utcnow().timestamp()}"
        )
        return {"analysis": response.message}
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return {"analysis": f"Sorry, I couldn't analyze this failure automatically. Error: {str(e)}"}

@router.post("/test/{operation_id}")
async def test_api(operation_id: str, session_id: str = "default"):
    api = meta_engine.get_api_details(operation_id)
    if not api:
        raise HTTPException(status_code=404, detail="API not found")
    
    await dashboard_logger.log(session_id, "info", f"Executing test for {operation_id}")
    curl_command = "No cURL generated"
    try:
        await dashboard_logger.log(session_id, "thinking", f"Generating realistic payload for {operation_id}...")
        payload = await meta_engine.generate_payload_template(operation_id)
        
        async def execute_request(current_payload):
            safe_payload = json.dumps(current_payload).replace("'", "'\\''")
            base_url = meta_engine.base_url_map.get(operation_id, "http://localhost:8000")
            url = f"{base_url}{api['path']}"
            method = api['method'].upper()
            curl = f"curl -X {method} '{url}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{safe_payload}'"
            
            async with httpx.AsyncClient() as client:
                resp = await client.request(method, url, json=current_payload, timeout=45.0)
                return resp, curl

        # ─── First Attempt ───
        resp, curl_command = await execute_request(payload)
        await dashboard_logger.log(session_id, "info", f"Attempt 1 Status: {resp.status_code}")
        
        # ─── Self-Healing Loop (Retry on Logical/Schema Errors) ───
        if resp.status_code in [400, 409, 422]:
            error_msg = resp.text[:500]
            await dashboard_logger.log(session_id, "thinking", f"Self-Healing: Analyzing error: {resp.status_code}")
            
            # Agent Reasons about the error and refines the payload
            refined_payload = await meta_engine.refine_payload(operation_id, payload, error_msg)
            
            if refined_payload != payload:
                await dashboard_logger.log(session_id, "thinking", "Attempting recovery with corrected payload...")
                resp, curl_command = await execute_request(refined_payload)
                payload = refined_payload # Update payload for final response
                await dashboard_logger.log(session_id, "info", f"Attempt 2 Status: {resp.status_code}")

        if resp.status_code in [200, 201, 204]:
            await dashboard_logger.log(session_id, "success", f"✅ Test Passed for {operation_id}")
            return {"status": "success", "code": resp.status_code, "data": resp.json() if resp.text else {}, "payload": payload, "curl": curl_command}
        else:
            await dashboard_logger.log(session_id, "error", f"❌ Test Failed: {resp.status_code}")
            return {"status": "failed", "code": resp.status_code, "error": resp.text, "payload": payload, "curl": curl_command}
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}" if str(e) else type(e).__name__
        logger.error(f"Test Execution Error for {operation_id}: {error_msg}")
        logger.error(traceback.format_exc())
        await dashboard_logger.log(session_id, "error", f"Execution Error: {error_msg}")
        return {"status": "error", "error": error_msg, "payload": {}, "curl": curl_command}

@router.post("/batch")
async def trigger_batch(request: BatchRequest, background_tasks: BackgroundTasks):
    service_name = request.service
    session_id = request.sessionId
    
    service_url = SERVICES.get(service_name, {}).get("url")
    if not service_url:
        raise HTTPException(status_code=404, detail=f"Service '{service_name}' not found")
        
    ops = [op for op, burl in meta_engine.base_url_map.items() if burl == service_url]
    background_tasks.add_task(run_batch_task, service_name, ops, session_id)
    
    return {"status": "started", "service": service_name, "total": len(ops)}

async def run_batch_task(service_name: str, ops: List[str], session_id: str):
    await dashboard_logger.log(session_id, "info", f"🚀 Starting Real Batch Test for {service_name} ({len(ops)} operations)")
    
    results = []
    for op in ops:
        try:
            res = await test_api(op, session_id)
            results.append({"op": op, "result": res})
            await dashboard_logger.log(session_id, "test_result", {"op": op, "result": res})
        except Exception as e:
            logger.error(f"Unexpected error in batch loop for {op}: {e}")
            error_res = {"status": "error", "error": str(e)}
            results.append({"op": op, "result": error_res})
            await dashboard_logger.log(session_id, "test_result", {"op": op, "result": error_res})
        
    await dashboard_logger.log(session_id, "success", f"✅ Batch Complete for {service_name}.")
    
    try:
        if db_client.db is not None:
            collection = db_client.db["test_reports"]
            report = {
                "service": service_name,
                "timestamp": datetime.utcnow(),
                "session_id": session_id,
                "total": len(ops),
                "passed": sum(1 for r in results if r["result"].get("status") == "success"),
                "results": results
            }
            collection.insert_one(report)
            logger.info(f"Saved test report to MongoDB for {service_name}")
    except Exception as e:
        logger.error(f"Failed to save test report to MongoDB: {e}")

@router.get("/events/{session_id}")
async def stream_meta_events(session_id: str):
    async def event_generator():
        queue = dashboard_logger.get_queue(session_id)
        yield f"data: {json.dumps({'time': time.strftime('%H:%M:%S'), 'type': 'info', 'content': 'SSE Stream Connected'})}\n\n"
        
        while True:
            try:
                log_item = await asyncio.wait_for(queue.get(), timeout=20.0)
                yield f"data: {json.dumps(log_item)}\n\n"
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
            except Exception as e:
                logger.error(f"SSE Error: {e}")
                break
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")
