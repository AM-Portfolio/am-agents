"""
registry.py
===========
Central tool registry for the FinanceAgent.

Contains:
  - TOOL_REGISTRY      : list of OpenAI-compatible tool schemas
  - OPENAPI_EXECUTOR_MAP: operationId → _meta dict for HTTP routing
  - register_tool()    : decorator for hand-written tools
  - register_openapi_tools() : bulk-registers all tools from parsed OpenAPI specs
  - execute_tool()     : dispatch a tool call by name (hand-written OR openapi)
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List

from shared.observability.agent_log import log_agent_error, log_agent_warning
from shared.observability.log_events import AgentLogEvent
from shared.observability.logging_setup import get_logger

logger = get_logger("tools.registry")

# ─── Registries ───────────────────────────────────────────────────────────────

# OpenAI-compatible tool schema list – sent to the LLM
TOOL_REGISTRY: List[Dict[str, Any]] = []

# Hand-written tool implementations  {fn_name → callable}
_TOOL_IMPL: Dict[str, Callable] = {}

# OpenAPI-generated HTTP routing table  {operationId → _meta dict}
OPENAPI_EXECUTOR_MAP: Dict[str, Dict[str, str]] = {}


# ─── Hand-Written Tool Decorator ─────────────────────────────────────────────


def register_tool(description: str, parameters: Dict[str, Any] = None):
    """
    Decorator factory that registers a function as a hand-written agent tool.

    Usage:
        @register_tool(description="...", parameters={...})
        def my_tool(arg: str) -> str: ...
    """
    def decorator(fn: Callable) -> Callable:
        tool_def = {
            "type": "function",
            "function": {
                "name": fn.__name__,
                "description": description,
                "parameters": parameters or {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }
        # Avoid double-registration (e.g. on module reload)
        if not any(t.get("function", {}).get("name") == fn.__name__ for t in TOOL_REGISTRY):
            TOOL_REGISTRY.append(tool_def)
        _TOOL_IMPL[fn.__name__] = fn
        return fn

    return decorator


# ─── OpenAPI Bulk Registration ────────────────────────────────────────────────


def register_openapi_tools(apis: List[Dict[str, Any]]) -> int:
    """
    Bulk-register tools generated from OpenAPI specs.

    Accepts the list produced by tools.openapi_tool_generator.spec_to_tools().
    Each entry must have a '_meta' key with routing info (method, path, base_url).

    Args:
        apis: List of tool schema dicts (OpenAI format + '_meta').

    Returns:
        Number of newly registered tools.
    """
    registered = 0

    for tool in apis:
        if tool.get("type") != "function":
            continue

        fn = tool["function"]
        op_id: str = fn.get("name", "")

        if not op_id:
            continue

        # Skip if already registered (e.g. a hand-written tool with same name)
        if any(t.get("function", {}).get("name") == op_id for t in TOOL_REGISTRY):
            logger.debug("register_openapi_tools: skipping duplicate '%s'", op_id)
            continue

        # Store full schema in TOOL_REGISTRY (without _meta so LLM never sees it)
        public_schema = {k: v for k, v in tool.items() if k != "_meta"}
        TOOL_REGISTRY.append(public_schema)

        # Store routing in executor map
        meta = tool.get("_meta", {})
        if meta:
            OPENAPI_EXECUTOR_MAP[op_id] = meta

        registered += 1

    logger.info(
        "register_openapi_tools: added %d tools. "
        "Total in TOOL_REGISTRY: %d, OPENAPI_EXECUTOR_MAP: %d",
        registered, len(TOOL_REGISTRY), len(OPENAPI_EXECUTOR_MAP),
    )
    return registered


# ─── Tool Execution ───────────────────────────────────────────────────────────


async def execute_tool(name: str, args: Dict[str, Any]) -> str:
    if name == "get_holding_details":
        name = "get_holding_detail"

    """
    Dispatch a tool call by name (ASYNCHRONOUS).

    Priority:
      1. Hand-written tools (_TOOL_IMPL)
      2. OpenAPI-generated tools (OPENAPI_EXECUTOR_MAP)
      3. Unknown -> error string
    """
    import time
    start_time = time.time()
    result = ""
    
    try:
        # 1. Hand-written tool
        impl = _TOOL_IMPL.get(name)
        if impl:
            try:
                if asyncio.iscoroutinefunction(impl):
                    result = await impl(**args)
                else:
                    result = impl(**args)
            except Exception as exc:
                log_agent_error(logger, AgentLogEvent.TOOL_EXECUTE_ERROR, error=exc, tool=name)
                result = f"Error executing tool '{name}': {exc}"
            return result
            
        # 2. OpenAPI-generated tool
        meta = OPENAPI_EXECUTOR_MAP.get(name)
        if meta:
            from tools.openapi_tool_generator import execute_openapi_tool
            try:
                result = await execute_openapi_tool(meta, args)
            except Exception as exc:
                logger.error("execute_tool: openapi tool '%s' raised %s", name, exc)
                result = f'{{"error": "Tool execution failed: {exc}"}}'
            return result
            
        # 3. Unknown
        log_agent_warning(logger, AgentLogEvent.TOOL_UNKNOWN, tool=name, args=args)
        result = f"Error: Unknown tool '{name}'"
        return result
        
    finally:
        try:
            from shared.llm.client import emit_langfuse_span
            asyncio.create_task(emit_langfuse_span(f"tool.{name}", args, result, start_time))
        except Exception as e:
            logger.error(f"Failed to emit langfuse span: {e}")


def _run_async(coro_fn, *args) -> str:
    """Run an async coroutine in a fresh event loop (for thread executor context)."""
    new_loop = asyncio.new_event_loop()
    try:
        return new_loop.run_until_complete(coro_fn(*args))
    finally:
        new_loop.close()
