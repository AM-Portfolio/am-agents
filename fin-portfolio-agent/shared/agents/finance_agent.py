"""
FinanceAgent — LangGraph ReAct agent.
Tools are discovered and executed via am-mcp-server (no local data-tool registry).
"""
import json
import logging
import asyncio
import re
import uuid
from typing import TypedDict, Annotated, List, Dict, Any, Optional
import operator

from langchain_core.messages import (
    HumanMessage, BaseMessage, ToolMessage, AIMessage
)
from langgraph.graph import StateGraph, END

from shared.llm.client import llm_client
from shared.clients.am_mcp_client import am_mcp_client
from shared.formatters.artifact_resolver import resolve_artifact
from shared.schemas.intent import AiIntentResponse
from shared.context.request_context import user_id_var, trace_id_var, session_id_var
from shared.core.config import settings
from shared.prompts import get_system_prompt
from shared.observability import tracer as lf
from shared.observability.context import get_obs_context, set_obs_context
from shared.observability.sanitize import sanitize_payload

logger = logging.getLogger(__name__)

# Optional API-testing tools only (not portfolio data).
if settings.ENABLE_API_TESTING:
    try:
        import am_fin_api_testing.tools.meta_tools       # noqa
        logger.info("API Testing module loaded.")
    except ImportError as e:
        logger.error("Failed to load API Testing module: %s", e)

TOOL_TIMEOUT_SECONDS = settings.MCP_TOOL_TIMEOUT_SECONDS

_API_TESTING_APPENDIX = """
2. **API Testing (Meta-Tools)**: You can explore and test any API registry (Swagger/OpenAPI).
   - Use `register_api_spec` if you need to load a new Swagger JSON file from the filesystem.
   - Use `search_apis` to find relevant endpoints.
   - Use `get_api_workflow` to understand dependencies.
   - Use `generate_payload` to see how to structure a request.
   - Use `execute_api` to perform the test.
   - Use `validate_response` to ensure the API meets its schema.
"""


def resolve_system_prompt() -> str:
    """Load system prompt via PROMPT_SOURCE (langfuse|file); append API-testing if enabled."""
    template = get_system_prompt()
    ctx = get_obs_context()
    if ctx is not None:
        ctx.prompt_name = template.name
        ctx.prompt_version = template.version
        ctx.prompt_source = template.source
        ctx.prompt_label = template.label
        set_obs_context(ctx)
    content = template.content
    if settings.ENABLE_API_TESTING and "search_apis" not in content:
        content = content.rstrip() + "\n" + _API_TESTING_APPENDIX
    return content


class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    tools_called: List[str]
    final_response: Optional[str]


async def _mcp_openai_tools() -> List[Dict[str, Any]]:
    tools = await am_mcp_client.list_tools_openai()
    if settings.ENABLE_API_TESTING:
        from shared.tools.registry import TOOL_REGISTRY
        for t in TOOL_REGISTRY:
            name = (t.get("function") or {}).get("name")
            if name and name not in am_mcp_client.blocklist:
                tools.append(t)
    return tools


async def agent_node(state: AgentState) -> Dict[str, Any]:
    """LLM decides what tools to call next based on current state."""
    messages = state["messages"]

    with lf.span("retrieve_tools", input={"source": "am-mcp-server"}) as retrieve_obs:
        relevant_tools = await _mcp_openai_tools()
        lf.end_span(retrieve_obs, output={"tool_count": len(relevant_tools)})

    system_prompt = resolve_system_prompt()
    payload = [{"role": "system", "content": system_prompt}]
    for m in messages:
        if isinstance(m, HumanMessage):
            payload.append({"role": "user", "content": m.content})
        elif isinstance(m, AIMessage):
            d = {"role": "assistant", "content": m.content or ""}
            if m.additional_kwargs.get("tool_calls"):
                d["tool_calls"] = m.additional_kwargs["tool_calls"]
            payload.append(d)
        elif isinstance(m, ToolMessage):
            payload.append({
                "role": "tool",
                "content": m.content,
                "tool_call_id": m.tool_call_id,
                "name": m.name
            })

    ctx = get_obs_context()
    request_id = ctx.request_id if ctx else "fin-request"
    response = await llm_client.chat(
        messages=payload,
        temperature=0.0,
        tools=relevant_tools or None,
        tool_choice="auto" if relevant_tools else None,
        request_id=request_id,
    )

    if isinstance(response, dict) and response.get("tool_calls"):
        ai_msg = AIMessage(
            content=response.get("content") or "",
            additional_kwargs={"tool_calls": response["tool_calls"]}
        )
        return {"messages": [ai_msg], "tools_called": state.get("tools_called", [])}

    text = str(response)
    synthetic = _parse_text_tool_calls(text, relevant_tools)
    if synthetic:
        ai_msg = AIMessage(content="", additional_kwargs={"tool_calls": synthetic})
        return {"messages": [ai_msg], "tools_called": state.get("tools_called", [])}

    if _looks_like_invented_tools_only(text, relevant_tools):
        fixed = (
            "I can only use the finance MCP tools available in this session "
            "(for example get_portfolio_summary, get_holdings, get_top_movers, get_market_movers). "
            "Please rephrase your question and I will call the correct tool."
        )
        return {
            "messages": [AIMessage(content=fixed)],
            "final_response": fixed,
            "tools_called": state.get("tools_called", []),
        }

    return {
        "messages": [AIMessage(content=text)],
        "final_response": text,
        "tools_called": state.get("tools_called", []),
    }


_TEXT_TOOL_RE = re.compile(
    r"(?m)^\s*([a-zA-Z_][a-zA-Z0-9_]*)\((.*)\)\s*$"
)
_TOOL_CODE_RE = re.compile(
    r"<tool_code>\s*(\{.*?\})\s*</tool_code>",
    re.DOTALL | re.IGNORECASE,
)
_TOOL_CODE_NAME_RE = re.compile(
    r"<tool_code>\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*</tool_code>",
    re.IGNORECASE,
)
_MARKDOWN_TOOL_JSON_RE = re.compile(
    r"```(?:json)?\s*(\{(?:[^{}]|\{[^{}]*\})*\})\s*```",
    re.DOTALL | re.IGNORECASE,
)


def _looks_like_invented_tools_only(text: str, available_tools: List[Dict[str, Any]]) -> bool:
    if not text or not text.strip():
        return False
    if (
        _TOOL_CODE_RE.search(text)
        or _TOOL_CODE_NAME_RE.search(text)
        or _MARKDOWN_TOOL_JSON_RE.search(text)
    ):
        return False
    known = {
        t.get("function", {}).get("name")
        for t in available_tools
        if t.get("type") == "function" and t.get("function", {}).get("name")
    }
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        return False
    shaped = 0
    for line in lines:
        m = _TEXT_TOOL_RE.match(line)
        if not m:
            return False
        shaped += 1
        if m.group(1) in known:
            return False
    return shaped > 0


def _calls_from_tool_json_blobs(text: str, known: set[str]) -> List[Dict[str, Any]]:
    calls: List[Dict[str, Any]] = []
    blobs: List[str] = []
    for match in _TOOL_CODE_RE.finditer(text):
        blobs.append(match.group(1))
    for match in _MARKDOWN_TOOL_JSON_RE.finditer(text):
        blobs.append(match.group(1))
    stripped = text.strip()
    if stripped.startswith("{") and (
        '"name"' in stripped or '"tool"' in stripped
    ):
        blobs.append(stripped)
    for raw in blobs:
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        name = obj.get("name") or obj.get("tool")
        if not name or name not in known:
            logger.warning("Rejected unknown tool json name: %s", name)
            continue
        args_obj = obj.get("arguments") if isinstance(obj.get("arguments"), dict) else {}
        if not args_obj and isinstance(obj.get("parameters"), dict):
            args_obj = obj["parameters"]
        calls.append(
            {
                "id": f"call_{uuid.uuid4().hex[:12]}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args_obj)},
            }
        )
    # <tool_code>get_top_movers</tool_code> (name only, no JSON)
    for match in _TOOL_CODE_NAME_RE.finditer(text):
        name = match.group(1)
        if name not in known:
            logger.warning("Rejected unknown tool_code name: %s", name)
            continue
        if any(c["function"]["name"] == name for c in calls):
            continue
        calls.append(
            {
                "id": f"call_{uuid.uuid4().hex[:12]}",
                "type": "function",
                "function": {"name": name, "arguments": "{}"},
            }
        )
    return calls


def _parse_tool_code_blocks(text: str, available_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Parse <tool_code> / markdown JSON tool intents."""
    if not text or not available_tools:
        return []
    known = {
        t.get("function", {}).get("name")
        for t in available_tools
        if t.get("type") == "function" and t.get("function", {}).get("name")
    }
    return _calls_from_tool_json_blobs(text, known)


def _parse_text_tool_calls(text: str, available_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    xml_calls = _parse_tool_code_blocks(text, available_tools)
    if xml_calls:
        return xml_calls
    if not text or not available_tools:
        return []
    known = {
        t.get("function", {}).get("name")
        for t in available_tools
        if t.get("type") == "function" and t.get("function", {}).get("name")
    }
    calls: List[Dict[str, Any]] = []
    unknown: List[str] = []
    tool_shaped_lines = 0
    for line in text.strip().splitlines():
        m = _TEXT_TOOL_RE.match(line.strip())
        if not m:
            continue
        tool_shaped_lines += 1
        name, raw_args = m.group(1), m.group(2).strip()
        if name not in known:
            unknown.append(name)
            continue
        args_obj: Dict[str, Any] = {}
        if raw_args:
            if raw_args.startswith("{"):
                try:
                    args_obj = json.loads(raw_args)
                except json.JSONDecodeError:
                    args_obj = {}
            else:
                for part in re.findall(
                    r'([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*("([^"]*)"|\'([^\']*)\'|[^,]+)',
                    raw_args,
                ):
                    key, _full, dq, sq = part[0], part[1], part[2], part[3]
                    val = dq if dq else (sq if sq else part[1].strip().strip("\"'"))
                    args_obj[key] = val
        calls.append(
            {
                "id": f"call_{uuid.uuid4().hex[:12]}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args_obj)},
            }
        )
    if tool_shaped_lines and not calls and unknown:
        logger.warning("Rejected unknown text tool calls: %s", unknown)
        return []
    return calls


async def tools_node(state: AgentState) -> Dict[str, Any]:
    """Execute tool calls via am-mcp-server."""
    last_msg = state["messages"][-1]
    tool_calls = last_msg.additional_kwargs.get("tool_calls", [])
    tools_executed = list(state.get("tools_called", []))
    summary_mode = settings.LANGFUSE_TOOL_PAYLOAD_MODE != "full"

    async def run_one(call) -> ToolMessage:
        func = call["function"]
        name = func["name"]
        raw_args = func.get("arguments", "{}")
        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args

        tools_executed.append(name)
        logger.debug(
            "tool_call",
            extra={"tool": name, "args": args, "trace_id": trace_id_var.get()}
        )
        span_input = {"tool": name, "args": args if not summary_mode else list(args.keys())}
        with lf.span(f"tool.{name}", input=span_input) as tool_obs:
            try:
                result_obj = await asyncio.wait_for(
                    am_mcp_client.call_tool(name, args),
                    timeout=TOOL_TIMEOUT_SECONDS,
                )
                # Defense in depth if MCP returns envelope string/dict.
                from shared.clients.am_mcp_client import _unwrap_mcp_envelope

                result_obj = _unwrap_mcp_envelope(result_obj)
                result = result_obj if isinstance(result_obj, str) else json.dumps(result_obj)
                out = (
                    {"tool": name, "ok": True, "chars": len(str(result))}
                    if summary_mode
                    else sanitize_payload({"tool": name, "result": result_obj})
                )
                lf.end_span(tool_obs, output=out)
            except asyncio.TimeoutError:
                result = json.dumps({
                    "error": f"Tool '{name}' timed out after {TOOL_TIMEOUT_SECONDS}s",
                })
                lf.end_span(tool_obs, error=f"timeout after {TOOL_TIMEOUT_SECONDS}s")
            except Exception as e:
                logger.error("Error executing tool %s: %s", name, e)
                result = json.dumps({"error": str(e)})
                lf.end_span(tool_obs, error=str(e))

        return ToolMessage(tool_call_id=call["id"], content=str(result), name=name)

    results = await asyncio.gather(*[run_one(c) for c in tool_calls])
    return {"messages": list(results), "tools_called": tools_executed}


def should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.additional_kwargs.get("tool_calls"):
        return "tools"
    return END


def _build_graph():
    wf = StateGraph(AgentState)
    wf.add_node("agent", agent_node)
    wf.add_node("tools", tools_node)
    wf.set_entry_point("agent")
    wf.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    wf.add_edge("tools", "agent")
    return wf.compile()


_graph = _build_graph()


class FinanceAgent:

    async def run(
        self,
        message: str,
        history: List[Dict[str, str]],
        user_id: str,
        session_id: str,
        trace_id: str,
    ) -> AiIntentResponse:
        user_id_var.set(user_id)
        session_id_var.set(session_id)
        trace_id_var.set(trace_id)

        lc_messages: List[BaseMessage] = []
        for msg in history[-10:]:
            if msg["role"] == "user":
                lc_messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                lc_messages.append(AIMessage(content=msg["content"]))
        lc_messages.append(HumanMessage(content=message))

        initial_state: AgentState = {
            "messages": lc_messages,
            "tools_called": [],
            "final_response": None
        }

        try:
            with lf.span("intent_resolve", input={"message": message[:500]}) as _prep:
                lf.end_span(_prep, output={"history_len": len(history)})
            final_state = await _graph.ainvoke(initial_state, config={"recursion_limit": 50})
        except Exception as e:
            logger.error("Agent error: %s", e, extra={"trace_id": trace_id, "userId": user_id})
            return AiIntentResponse(
                message="I ran into an issue processing your request. Please try again.",
                artifactType="error.v1",
                data={"error": str(e), "userId": user_id},
                sessionId=session_id,
                toolsUsed=[],
                traceId=trace_id,
            )

        tools_called = final_state.get("tools_called", [])
        answer = final_state.get("final_response") or "I couldn't find a specific answer for that."

        tool_data: dict = {}
        for msg in final_state.get("messages", []):
            msg_type = getattr(msg, "type", None)
            msg_name = getattr(msg, "name", None)
            content = getattr(msg, "content", None)
            if msg_type == "tool" and msg_name and content:
                try:
                    tool_data[msg_name] = json.loads(content)
                except (ValueError, TypeError):
                    tool_data[msg_name] = {"raw": str(content)}

        with lf.span("artifact_resolve", input={"tools": tools_called}) as intent_obs:
            artifact_type, data = resolve_artifact(tools_called, tool_data)
            lf.end_span(intent_obs, output={"artifactType": artifact_type})

        return AiIntentResponse(
            message=answer,
            artifactType=artifact_type,
            data=data,
            sessionId=session_id,
            toolsUsed=tools_called,
            traceId=trace_id,
        )

    async def run_stream(
        self,
        message: str,
        history: List[Dict[str, str]],
        user_id: str,
        session_id: str,
        trace_id: str,
    ):
        user_id_var.set(user_id)
        session_id_var.set(session_id)
        trace_id_var.set(trace_id)

        lc_messages: List[BaseMessage] = []
        for msg in history[-10:]:
            if msg["role"] == "user":
                lc_messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                lc_messages.append(AIMessage(content=msg["content"]))
        lc_messages.append(HumanMessage(content=message))

        initial_state: AgentState = {
            "messages": lc_messages,
            "tools_called": [],
            "final_response": None
        }

        tokens_yielded = False
        async for event in _graph.astream_events(initial_state, version="v1", config={"recursion_limit": 50}):
            kind = event["event"]

            if kind == "on_chat_model_stream":
                content = event["data"]["chunk"].content
                if content:
                    tokens_yielded = True
                    yield json.dumps({"type": "token", "content": content})

            elif kind == "on_tool_start":
                yield json.dumps({"type": "status", "content": f"Executing {event['name']}..."})

            elif kind == "on_tool_end":
                yield json.dumps({"type": "status", "content": f"{event['name']} completed."})

            elif kind == "on_chain_end":
                final_state = event["data"].get("output")
                if isinstance(final_state, dict):
                    tools_called = final_state.get("tools_called", [])

                    if "final_response" in final_state:
                        yield json.dumps({
                            "type": "final",
                            "tools_used": tools_called,
                            "trace_id": trace_id,
                            "answer": final_state.get("final_response")
                        })

                        if not tokens_yielded and final_state.get("final_response"):
                            yield json.dumps({"type": "token", "content": final_state["final_response"]})
                            tokens_yielded = True


finance_agent = FinanceAgent()
