"""
FinanceAgent — LangGraph ReAct agent.
Replaces the monolithic ChatAgent in chatbot/bot.py with:
  - Tool registry integration (all tools loaded dynamically)
  - Parallel tool execution via asyncio.gather
  - Circuit breaker (timeout per tool)
  - ContextVar aware (userId/traceId available in all tools)
  - Intent formatting via deterministic IntentFormatter
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
from shared.formatters.user_response import sanitize_user_response
from shared.prompts.system import get_system_prompt
from shared.schemas.intent import AiIntentResponse, WidgetId
from shared.context.request_context import user_id_var, trace_id_var, session_id_var
from shared.core.config import settings
from shared.streaming.events import (
    token_event, tool_start_event, tool_end_event,
    widget_event, done_event, error_event, cancelled_event
)
from shared.agents.llm_tool_coercion import coerce_llm_tool_response, describe_coercion
from shared.observability.agent_log import log_agent_error, log_agent_event, log_agent_warning
from shared.observability.langfuse_tracer import fin_tracer
from shared.observability.log_events import AgentLogEvent
from shared.observability.logging_setup import get_logger


logger = get_logger("finance_agent")

TOOL_DATA_CACHE = {} # trace_id -> dict

# ─── Dynamic Module Loading ──────────────────────────────────────────────────

if settings.ENABLE_PORTFOLIO_ANALYSIS:
    try:
        import am_fin_portfolio_analysis.tools.portfolio_tools  # noqa
        import am_fin_portfolio_analysis.tools.analysis_tools   # noqa
        import am_fin_portfolio_analysis.tools.trade_tools      # noqa
        logger.info("Portfolio Analysis module loaded.")
        log_agent_event(logger, AgentLogEvent.MODULE_LOAD, module="portfolio_analysis")
        try:
            from shared.mcp_ext.tools import register_mcp_tools
            mcp_count = register_mcp_tools(override=True)
            log_agent_event(
                logger,
                AgentLogEvent.MODULE_LOAD,
                module="mcp_tools",
                tool_count=mcp_count,
            )
        except Exception as mcp_err:
            log_agent_error(
                logger,
                AgentLogEvent.MODULE_LOAD_ERROR,
                error=mcp_err,
                module="mcp_tools",
                exc_info=True,
            )
    except ImportError as e:
        log_agent_error(
            logger,
            AgentLogEvent.MODULE_LOAD_ERROR,
            error=e,
            module="portfolio_analysis",
            exc_info=True,
        )

if settings.ENABLE_API_TESTING:
    try:
        import am_fin_api_testing.tools.meta_tools       # noqa
        logger.info("✅ API Testing module loaded.")
    except ImportError as e:
        logger.error(f"❌ Failed to load API Testing module: {e}")

TOOL_TIMEOUT_SECONDS = settings.TOOL_TIMEOUT_SECONDS


# ─── LangGraph State ─────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    tools_called: List[str]          # accumulates tool names executed this turn
    final_response: Optional[str]


# ─── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = get_system_prompt(
    enable_portfolio=settings.ENABLE_PORTFOLIO_ANALYSIS,
    enable_api_testing=settings.ENABLE_API_TESTING,
)


# ─── Agent Node ───────────────────────────────────────────────────────────────

async def agent_node(state: AgentState) -> Dict[str, Any]:
    """LLM decides what tools to call next based on current state."""
    messages = state["messages"]

    # ── Dynamic tool retrieval via vector search ──────────────────────────────
    # Extract the last few messages to use as retrieval context.
    # This ensures that "execute now" or "go ahead" still find the relevant tools.
    search_context = []
    msgs_for_context = messages[-3:]  # Last 3 messages for context
    for m in msgs_for_context:
        if isinstance(m, (HumanMessage, AIMessage)):
            search_context.append(str(m.content))
    
    retrieval_query = "\n".join(search_context)

    try:
        from shared.tools.tool_index import retrieve_tools
        relevant_tools = retrieve_tools(retrieval_query, top_k=10) if retrieval_query else TOOL_REGISTRY
    except Exception:
        # Fallback to full registry if retrieval fails
        relevant_tools = TOOL_REGISTRY

    if not relevant_tools:
        relevant_tools = TOOL_REGISTRY

    # Build message payload
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
                "name": m.name
            })

    log_agent_event(
        logger,
        AgentLogEvent.LLM_REQUEST,
        tool_count=len(relevant_tools),
        message_count=len(payload),
        tools=[t.get("function", {}).get("name") for t in relevant_tools[:8]],
    )

    response = await llm_client.chat(
        messages=payload,
        temperature=0.0,
        tools=relevant_tools,       # ← only top-k relevant tools, not all of them
        tool_choice="auto",
        request_id=trace_id_var.get() or "fin-request",
    )

    uid = user_id_var.get() or "anonymous"
    raw_response = response
    response = coerce_llm_tool_response(
        response,
        relevant_tools,
        default_args={"userId": uid} if uid else None,
    )
    coercion = describe_coercion(raw_response, response)
    if coercion:
        log_agent_event(logger, AgentLogEvent.LLM_TEXT_TOOL_COERCED, **coercion)
        await fin_tracer.record_span(
            trace_id_var.get() or "fin-request",
            "agent.text_tool_coercion",
            input_data=coercion.get("raw_text"),
            output_data=coercion.get("tool_calls"),
            metadata=coercion,
        )

    if isinstance(response, dict) and response.get("tool_calls"):
        log_agent_event(
            logger,
            AgentLogEvent.LLM_TOOL_CALLS,
            tools=[c.get("function", {}).get("name") for c in response["tool_calls"]],
        )
        ai_msg = AIMessage(
            content=response.get("content") or "",
            additional_kwargs={"tool_calls": response["tool_calls"]}
        )
        return {"messages": [ai_msg], "tools_called": state.get("tools_called", [])}

    text = sanitize_user_response(str(response))
    log_agent_event(logger, AgentLogEvent.LLM_TEXT_RESPONSE, preview=text[:200])
    return {"messages": [AIMessage(content=text)], "final_response": text, "tools_called": state.get("tools_called", [])}


# ─── Tools Node (Parallel + Circuit Breaker) ──────────────────────────────────

async def tools_node(state: AgentState) -> Dict[str, Any]:
    """Execute all requested tool calls in parallel with per-call timeout."""
    last_msg = state["messages"][-1]
    tool_calls = last_msg.additional_kwargs.get("tool_calls", [])
    tools_executed = list(state.get("tools_called", []))

    async def run_one(call) -> ToolMessage:
        func = call["function"]
        name = func["name"]
        raw_args = func.get("arguments", "{}")
        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        uid = user_id_var.get()
        if uid and uid not in {"anonymous", "-"}:
            args["userId"] = uid

        tools_executed.append(name)
        log_agent_event(logger, AgentLogEvent.TOOL_EXECUTE_START, tool=name, args=args)
        try:
            # We no longer need run_in_executor because execute_tool is now async
            # and handles both sync/async tools internally.
            result = await asyncio.wait_for(
                execute_tool(name, args),
                timeout=TOOL_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            result = json.dumps({"error": f"Tool '{name}' timed out after {TOOL_TIMEOUT_SECONDS}s", "fallback": True})
            log_agent_warning(
                logger,
                AgentLogEvent.TOOL_EXECUTE_ERROR,
                tool=name,
                reason="timeout",
                timeout_seconds=TOOL_TIMEOUT_SECONDS,
            )
        except Exception as e:
            log_agent_error(
                logger,
                AgentLogEvent.TOOL_EXECUTE_ERROR,
                error=e,
                tool=name,
                exc_info=True,
            )
            result = json.dumps({"error": str(e), "fallback": True})

        log_agent_event(
            logger,
            AgentLogEvent.TOOL_EXECUTE_END,
            tool=name,
            result_preview=str(result)[:200],
        )
        trace = trace_id_var.get()
        if trace:
            cached = TOOL_DATA_CACHE.setdefault(trace, {})
            try:
                cached[name] = json.loads(result) if isinstance(result, str) else result
            except (ValueError, TypeError, json.JSONDecodeError):
                cached[name] = result
        return ToolMessage(tool_call_id=call["id"], content=str(result), name=name)

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


def _extract_tool_data(messages: list) -> dict:
    """Collect parsed tool outputs from LangGraph ToolMessage entries."""
    tool_data: dict = {}
    for msg in messages:
        msg_type = getattr(msg, "type", None)
        msg_name = getattr(msg, "name", None)
        content = getattr(msg, "content", None)
        if msg_type == "tool" and msg_name and content is not None:
            try:
                tool_data[msg_name] = json.loads(content)
            except (ValueError, TypeError, json.JSONDecodeError):
                tool_data[msg_name] = content if isinstance(content, str) else {"raw": str(content)}
    return tool_data


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
        """
        Process a user message end-to-end and return a structured AiIntentResponse.
        """
        # Set context vars — all tools will read from these
        user_id_var.set(user_id)
        session_id_var.set(session_id)
        trace_id_var.set(trace_id)

        await fin_tracer.start_chat_trace(
            trace_id,
            user_id=user_id,
            session_id=session_id,
            user_message=message,
            system_prompt=SYSTEM_PROMPT,
        )
        log_agent_event(logger, AgentLogEvent.CHAT_START, message_preview=message[:200])

        # Build LangChain message list from session history
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
            final_state = await _graph.ainvoke(initial_state, config={"recursion_limit": 50})
        except Exception as e:
            err = str(e)
            if "connection attempts failed" in err.lower() or isinstance(e, OSError):
                log_agent_error(
                    logger,
                    AgentLogEvent.CHAT_ERROR,
                    error=e,
                    reason="network",
                    mcp=settings.MCP_BASE_URL,
                    litellm=settings.LITELLM_BASE_URL,
                    exc_info=True,
                )
            else:
                log_agent_error(
                    logger,
                    AgentLogEvent.CHAT_ERROR,
                    error=e,
                    exc_info=True,
                )
            return AiIntentResponse(
                message=f"I ran into an issue processing your request. Please try again.",
                widgetId=WidgetId.ERROR,
                widgetParams={"error": str(e), "userId": user_id},
                sessionId=session_id,
                toolsUsed=[],
                traceId=trace_id,
            )

        tools_called = final_state.get("tools_called", [])
        answer = sanitize_user_response(
            final_state.get("final_response") or "I couldn't find a specific answer for that."
        )

        # Collect ToolMessage return values so widgetParams can carry real data.
        tool_data = _extract_tool_data(final_state.get("messages", []))
        cached_data = TOOL_DATA_CACHE.pop(trace_id, {})
        tool_data.update(cached_data)
        widget_id, widget_params = resolve_intent(tools_called, user_id, tool_data)

        log_agent_event(
            logger,
            AgentLogEvent.CHAT_COMPLETE,
            tools_called=tools_called,
            widget_id=str(widget_id),
            answer_preview=answer[:200],
        )
        await fin_tracer.end_chat_trace(
            trace_id,
            user_id=user_id,
            session_id=session_id,
            answer=answer,
            tools_called=tools_called,
            widget_id=str(widget_id),
        )
        await fin_tracer.flush()

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
        user_id_var.set(user_id)
        session_id_var.set(session_id)
        trace_id_var.set(trace_id)

        await fin_tracer.start_chat_trace(
            trace_id,
            user_id=user_id,
            session_id=session_id,
            user_message=message,
            system_prompt=SYSTEM_PROMPT,
        )
        log_agent_event(logger, AgentLogEvent.CHAT_START, message_preview=message[:200])

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
        tools_called: list[str] = []
        final_answer = ""
        widget_id: str | None = None
        stream_error: str | None = None
        try:
            async for event in _graph.astream_events(initial_state, version="v1", config={"recursion_limit": 50}):
                kind = event["event"]
                # Do not stream raw LLM tokens — reasoning/planning must not reach the UI.
                if kind == "on_tool_start":
                    name = event.get("name", "unknown")
                    tools_called.append(name)
                    yield tool_start_event(name, trace_id).to_sse()
                elif kind == "on_tool_end":
                    name = event.get("name", "unknown")
                    yield tool_end_event(name, trace_id).to_sse()
                elif kind == "on_chain_end":
                    final_state = event["data"].get("output")
                    if isinstance(final_state, dict):
                        tc = final_state.get("tools_called", [])
                        if tc:
                            tools_called = list(dict.fromkeys(tools_called + tc))
                        if "final_response" in final_state:
                            final_answer = sanitize_user_response(
                                final_state.get("final_response") or ""
                            )
                            if not tokens_yielded and final_answer:
                                yield token_event(final_answer, trace_id).to_sse()
                                tokens_yielded = True
                            
                            # Fire widget event
                            tool_data = _extract_tool_data(final_state.get("messages", []))
                            tool_data.update(TOOL_DATA_CACHE.pop(trace_id, {}))
                            parsed = parse_agent_result(tc or tools_called, user_id, tool_data)
                            widget_id = parsed["widgetId"]
                            yield widget_event(
                                parsed["widgetId"], parsed["widgetParams"],
                                trace_id=trace_id, session_id=session_id
                            ).to_sse()
                            
                            # Fire done event
                            yield done_event(tc or tools_called, trace_id, session_id).to_sse()
        except asyncio.CancelledError:
            yield cancelled_event(trace_id, session_id).to_sse()
            raise
        except Exception as e:
            stream_error = str(e)
            log_agent_error(logger, AgentLogEvent.CHAT_STREAM_ERROR, error=e, exc_info=True)
            yield error_event(stream_error, trace_id, session_id).to_sse()
        finally:
            await fin_tracer.end_chat_trace(
                trace_id,
                user_id=user_id,
                session_id=session_id,
                answer=final_answer,
                tools_called=tools_called,
                widget_id=widget_id,
                error=stream_error,
            )
            await fin_tracer.flush()

finance_agent = FinanceAgent()
