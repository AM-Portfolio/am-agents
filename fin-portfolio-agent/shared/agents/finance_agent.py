"""
FinanceAgent — LangGraph ReAct agent.
Phase 1 upgrades:
  - Inbound GuardRail before LLM call
  - ToolResultCompressor on every tool observation
  - MCP tool catalog loaded on startup (Basket + all 27 tools)
  - Versioned system prompt from shared.prompts.system
  - Canonical SSE streaming events
  - userId-tenanted session history (AI_HISTORY_MAX_TURNS)
"""
import json
import logging
import asyncio
import contextvars
from typing import TypedDict, Annotated, List, Dict, Any, Optional
import operator

from langchain_core.messages import (
    HumanMessage, SystemMessage, BaseMessage, ToolMessage, AIMessage
)
from langgraph.graph import StateGraph, END

from shared.llm.client import llm_client
from shared.tools.registry import TOOL_REGISTRY, execute_tool
from shared.formatters.intent_formatter import resolve_intent, parse_agent_result
from shared.schemas.intent import AiIntentResponse, WidgetId
from shared.context.request_context import user_id_var, trace_id_var, session_id_var
from shared.core.config import settings
from shared.guardrail.inbound import check_inbound
from shared.tools.compressor import compress
from shared.streaming.events import (
    token_event, tool_start_event, tool_end_event,
    widget_event, done_event, error_event, cancelled_event,
)
from shared.prompts.system import get_system_prompt, PROMPT_ID, PROMPT_VERSION

logger = logging.getLogger(__name__)

# ─── Load MCP tools (Basket + all 27 tools) ───────────────────────────────────
try:
    from shared.mcp.tools import register_mcp_tools
    _mcp_count = register_mcp_tools()
    logger.info("Phase1: registered %d MCP tools", _mcp_count)
except Exception as _e:
    logger.warning("Phase1: MCP tool registration skipped: %s", _e)

# ─── Load optional analysis modules ───────────────────────────────────────────
if settings.ENABLE_PORTFOLIO_ANALYSIS:
    try:
        import am_fin_portfolio_analysis.tools.portfolio_tools  # noqa
        import am_fin_portfolio_analysis.tools.analysis_tools   # noqa
        import am_fin_portfolio_analysis.tools.trade_tools      # noqa
        logger.info("Portfolio Analysis module loaded.")
    except ImportError as e:
        logger.error("Failed to load Portfolio Analysis module: %s", e)

if settings.ENABLE_API_TESTING:
    try:
        import am_fin_api_testing.tools.meta_tools  # noqa
        logger.info("API Testing module loaded.")
    except ImportError as e:
        logger.error("Failed to load API Testing module: %s", e)

TOOL_TIMEOUT_SECONDS = 5.0
SYSTEM_PROMPT = get_system_prompt(
    enable_portfolio=settings.ENABLE_PORTFOLIO_ANALYSIS,
    enable_api_testing=settings.ENABLE_API_TESTING,
)


# ─── LangGraph State ──────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    tools_called: List[str]
    final_response: Optional[str]


# ─── Agent Node ───────────────────────────────────────────────────────────────

async def agent_node(state: AgentState) -> Dict[str, Any]:
    """LLM decides what tools to call next based on current state."""
    logger.debug("agent_node: promptId=%s version=%s", PROMPT_ID, PROMPT_VERSION)
    messages = state["messages"]

    search_context = []
    for m in messages[-3:]:
        if isinstance(m, (HumanMessage, AIMessage)):
            search_context.append(str(m.content))
    retrieval_query = "\n".join(search_context)

    try:
        from shared.tools.tool_index import retrieve_tools
        relevant_tools = retrieve_tools(retrieval_query, top_k=10) if retrieval_query else TOOL_REGISTRY
    except Exception:
        relevant_tools = TOOL_REGISTRY

    payload = [{"role": "system", "content": SYSTEM_PROMPT}]
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
                "name": m.name,
            })

    response = await llm_client.chat(
        messages=payload,
        temperature=0.0,
        tools=relevant_tools,
        tool_choice="auto",
    )

    # Handle FallbackLLMError structured error dict
    if isinstance(response, dict) and response.get("error"):
        err_msg = response.get("message", "LLM unavailable")
        return {
            "messages": [AIMessage(content=err_msg)],
            "final_response": err_msg,
            "tools_called": state.get("tools_called", []),
        }

    if isinstance(response, dict) and response.get("tool_calls"):
        ai_msg = AIMessage(
            content=response.get("content") or "",
            additional_kwargs={"tool_calls": response["tool_calls"]},
        )
        return {"messages": [ai_msg], "tools_called": state.get("tools_called", [])}

    text = str(response)
    return {"messages": [AIMessage(content=text)], "final_response": text, "tools_called": state.get("tools_called", [])}


# ─── Tools Node ───────────────────────────────────────────────────────────────

async def tools_node(state: AgentState) -> Dict[str, Any]:
    """Execute all requested tool calls in parallel with per-call timeout + compression."""
    last_msg = state["messages"][-1]
    tool_calls = last_msg.additional_kwargs.get("tool_calls", [])
    tools_executed = list(state.get("tools_called", []))

    async def run_one(call) -> ToolMessage:
        func = call["function"]
        name = func["name"]
        raw_args = func.get("arguments", "{}")
        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        tools_executed.append(name)
        logger.debug("tool_call: %s args=%s trace_id=%s", name, args, trace_id_var.get())
        try:
            result = await asyncio.wait_for(execute_tool(name, args), timeout=TOOL_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            result = json.dumps({"error": f"Tool '{name}' timed out after {TOOL_TIMEOUT_SECONDS}s", "fallback": True})
        except Exception as e:
            logger.error("Error executing tool %s: %s", name, e)
            result = json.dumps({"error": str(e), "fallback": True})

        # Phase 1: compress before sending to LLM
        compressed = compress(name, str(result))
        return ToolMessage(tool_call_id=call["id"], content=compressed, name=name)

    results = await asyncio.gather(*[run_one(c) for c in tool_calls])
    return {"messages": list(results), "tools_called": tools_executed}


# ─── Routing ──────────────────────────────────────────────────────────────────

def should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.additional_kwargs.get("tool_calls"):
        return "tools"
    return END


# ─── Graph ────────────────────────────────────────────────────────────────────

def _build_graph():
    wf = StateGraph(AgentState)
    wf.add_node("agent", agent_node)
    wf.add_node("tools", tools_node)
    wf.set_entry_point("agent")
    wf.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    wf.add_edge("tools", "agent")
    return wf.compile()

_graph = _build_graph()


# ─── Public Interface ─────────────────────────────────────────────────────────

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

        # Phase 1: Inbound GuardRail
        guard = check_inbound(message, user_id, trace_id)
        if guard.blocked:
            return AiIntentResponse(
                message=f"Request blocked: {guard.reason}",
                widgetId=WidgetId.ERROR,
                widgetParams={"reason": guard.reason, "traceId": trace_id},
                sessionId=session_id,
                toolsUsed=[],
                traceId=trace_id,
            )

        lc_messages: List[BaseMessage] = []
        for msg in history[-settings.AI_HISTORY_MAX_TURNS:]:
            if msg["role"] == "user":
                lc_messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                lc_messages.append(AIMessage(content=msg["content"]))
        lc_messages.append(HumanMessage(content=message))

        initial_state: AgentState = {
            "messages": lc_messages,
            "tools_called": [],
            "final_response": None,
        }

        try:
            final_state = await _graph.ainvoke(initial_state, config={"recursion_limit": 50})
        except Exception as e:
            logger.error("Agent error: %s trace_id=%s userId=%s", e, trace_id, user_id)
            return AiIntentResponse(
                message="I ran into an issue processing your request. Please try again.",
                widgetId=WidgetId.ERROR,
                widgetParams={"error": str(e), "traceId": trace_id},
                sessionId=session_id,
                toolsUsed=[],
                traceId=trace_id,
            )

        tools_called = final_state.get("tools_called", [])
        answer = final_state.get("final_response") or "I couldn't find a specific answer for that."

        tool_data: dict = {}
        for msg in final_state.get("messages", []):
            if getattr(msg, "type", None) == "tool" and getattr(msg, "name", None):
                try:
                    tool_data[msg.name] = json.loads(msg.content)
                except (ValueError, TypeError):
                    tool_data[msg.name] = {"raw": str(msg.content)}

        widget_id, widget_params = resolve_intent(tools_called, user_id, tool_data)
        return AiIntentResponse(
            message=answer,
            widgetId=widget_id,
            widgetParams=widget_params,
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
        """
        Streaming version. Yields SSE-formatted events:
        tool_start | tool_end | token | widget | done | error | cancelled
        """
        user_id_var.set(user_id)
        session_id_var.set(session_id)
        trace_id_var.set(trace_id)

        # Phase 1: Inbound GuardRail
        guard = check_inbound(message, user_id, trace_id)
        if guard.blocked:
            yield error_event(f"Request blocked: {guard.reason}", trace_id, session_id).to_sse()
            return

        lc_messages: List[BaseMessage] = []
        for msg in history[-settings.AI_HISTORY_MAX_TURNS:]:
            if msg["role"] == "user":
                lc_messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                lc_messages.append(AIMessage(content=msg["content"]))
        lc_messages.append(HumanMessage(content=message))

        initial_state: AgentState = {
            "messages": lc_messages,
            "tools_called": [],
            "final_response": None,
        }

        tools_called: List[str] = []
        tokens_yielded = False

        try:
            async for event in _graph.astream_events(initial_state, version="v1", config={"recursion_limit": 50}):
                kind = event["event"]

                if kind == "on_chat_model_stream":
                    content = event["data"]["chunk"].content
                    if content:
                        tokens_yielded = True
                        yield token_event(content, trace_id).to_sse()

                elif kind == "on_tool_start":
                    name = event.get("name", "unknown")
                    tools_called.append(name)
                    yield tool_start_event(name, trace_id).to_sse()

                elif kind == "on_tool_end":
                    yield tool_end_event(event.get("name", "unknown"), trace_id).to_sse()

                elif kind == "on_chain_end":
                    fs = event["data"].get("output")
                    if isinstance(fs, dict) and "final_response" in fs:
                        final_answer = fs.get("final_response") or ""
                        if not tokens_yielded and final_answer:
                            yield token_event(final_answer, trace_id).to_sse()
                            tokens_yielded = True

                        tc = fs.get("tools_called", tools_called)
                        parsed = parse_agent_result(tc, user_id)
                        yield widget_event(
                            parsed["widgetId"], parsed["widgetParams"],
                            trace_id=trace_id, session_id=session_id,
                        ).to_sse()
                        yield done_event(tc, trace_id, session_id).to_sse()
                        # Backward compat
                        yield json.dumps({"type": "final", "tools_used": tc, "trace_id": trace_id, "answer": final_answer}) + "\n"

        except asyncio.CancelledError:
            yield cancelled_event(trace_id, session_id).to_sse()
            raise
        except Exception as e:
            logger.error("run_stream error: %s trace_id=%s", e, trace_id)
            yield error_event(str(e), trace_id, session_id).to_sse()


finance_agent = FinanceAgent()
