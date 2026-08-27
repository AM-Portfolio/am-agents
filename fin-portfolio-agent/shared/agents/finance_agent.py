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
from shared.schemas.intent import AiIntentResponse, WidgetId
from shared.context.request_context import user_id_var, trace_id_var, session_id_var
from shared.core.config import settings
from shared.streaming.events import (
    token_event, tool_start_event, tool_end_event,
    widget_event, done_event, error_event, cancelled_event
)


logger = logging.getLogger(__name__)

TOOL_DATA_CACHE = {} # trace_id -> dict

# ─── Dynamic Module Loading ──────────────────────────────────────────────────

if settings.ENABLE_PORTFOLIO_ANALYSIS:
    try:
        import am_fin_portfolio_analysis.tools.portfolio_tools  # noqa
        import am_fin_portfolio_analysis.tools.analysis_tools   # noqa
        import am_fin_portfolio_analysis.tools.trade_tools      # noqa
        logger.info("✅ Portfolio Analysis module loaded.")
    except ImportError as e:
        logger.error(f"❌ Failed to load Portfolio Analysis module: {e}")

if settings.ENABLE_API_TESTING:
    try:
        import am_fin_api_testing.tools.meta_tools       # noqa
        logger.info("✅ API Testing module loaded.")
    except ImportError as e:
        logger.error(f"❌ Failed to load API Testing module: {e}")

TOOL_TIMEOUT_SECONDS = 5.0


# ─── LangGraph State ─────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    tools_called: List[str]          # accumulates tool names executed this turn
    final_response: Optional[str]


# ─── System Prompt ────────────────────────────────────────────────────────────

def _build_system_prompt() -> str:
    capabilities = []
    if settings.ENABLE_PORTFOLIO_ANALYSIS:
        capabilities.append("1. **Portfolio Analysis**: Use tools like get_portfolio_summary, analyze_etf_overlap, and count_etfs to answer financial questions.")
    if settings.ENABLE_API_TESTING:
        capabilities.append("2. **API Testing (Meta-Tools)**: You can explore and test any API registry (Swagger/OpenAPI).\n   - Use `register_api_spec` if you need to load a new Swagger JSON file from the filesystem.\n   - Use `search_apis` to find relevant endpoints.\n   - Use `get_api_workflow` to understand dependencies.\n   - Use `generate_payload` to see how to structure a request.\n   - Use `execute_api` to perform the test.\n   - Use `validate_response` to ensure the API meets its schema.")

    prompt = f"""You are an advanced Financial Intelligence Agent for the AM Portfolio platform.
You have access to the user's real portfolio data and an API testing "Meta-Tool" system.

DOMAIN CAPABILITIES:
{chr(10).join(capabilities)}
3. **Market News**: Use web_search for real-time market sentiment and stock news.

PRINCIPLES:
1. Always check the portfolio before giving advice — use get_portfolio_summary first if you don't have context.
2. **API Testing Lifecycle**: When asked to test an endpoint, follow these steps in your response:
   - **Step 1: Discovery**: Confirm that you have found the correct endpoint(s) and their requirements.
   - **Step 2: Execution**: State that you are calling the tool with specific parameters.
   - **Step 3: Status**: Immediately after tool execution, clearly state if it was a **PASS** (2xx status) or **FAIL** (non-2xx).
   - **Step 4: Analysis**: Provide a brief explanation of the result, especially if it failed.
3. Answer concisely with data-backed insights. Use beautiful markdown tables for complex data.

CRITICAL RULES:
- DO NOT say "I will now call...". Just call the tool immediately.
- If multiple tools are needed, call them all in the same turn.
- Never return generic answers. Always ground in the actual tool data.
- Ensure all important values are **bolded** for readability.
"""
    return prompt

SYSTEM_PROMPT = _build_system_prompt()


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

    response = await llm_client.chat(
        messages=payload,
        temperature=0.0,
        tools=relevant_tools,       # ← only top-k relevant tools, not all of them
        tool_choice="auto"
    )

    if isinstance(response, dict) and response.get("tool_calls"):
        ai_msg = AIMessage(
            content=response.get("content") or "",
            additional_kwargs={"tool_calls": response["tool_calls"]}
        )
        return {"messages": [ai_msg], "tools_called": state.get("tools_called", [])}

    text = str(response)
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

        tools_executed.append(name)
        logger.debug(
            "tool_call",
            extra={"tool": name, "args": args, "trace_id": trace_id_var.get()}
        )
        try:
            # We no longer need run_in_executor because execute_tool is now async
            # and handles both sync/async tools internally.
            result = await asyncio.wait_for(
                execute_tool(name, args),
                timeout=TOOL_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            result = json.dumps({"error": f"Tool '{name}' timed out after {TOOL_TIMEOUT_SECONDS}s", "fallback": True})
        except Exception as e:
            logger.error(f"Error executing tool {name}: {e}")
            result = json.dumps({"error": str(e), "fallback": True})

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
            logger.error(f"Agent error: {e}", extra={"trace_id": trace_id, "userId": user_id})
            return AiIntentResponse(
                message=f"I ran into an issue processing your request. Please try again.",
                widgetId=WidgetId.ERROR,
                widgetParams={"error": str(e), "userId": user_id},
                sessionId=session_id,
                toolsUsed=[],
                traceId=trace_id,
            )

        tools_called = final_state.get("tools_called", [])
        answer = final_state.get("final_response") or "I couldn't find a specific answer for that."

        # Collect ToolMessage return values so widgetParams can carry real data.
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

        cached_data = TOOL_DATA_CACHE.pop(trace_id, {})
        tool_data.update(cached_data)
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
        try:
            async for event in _graph.astream_events(initial_state, version="v1", config={"recursion_limit": 50}):
                kind = event["event"]
                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"].content
                    if chunk:
                        tokens_yielded = True
                        yield token_event(chunk, trace_id).to_sse()
                elif kind == "on_tool_start":
                    name = event.get("name", "unknown")
                    yield tool_start_event(name, trace_id).to_sse()
                elif kind == "on_tool_end":
                    name = event.get("name", "unknown")
                    yield tool_end_event(name, trace_id).to_sse()
                elif kind == "on_chain_end":
                    final_state = event["data"].get("output")
                    if isinstance(final_state, dict):
                        tc = final_state.get("tools_called", [])
                        if "final_response" in final_state:
                            final_answer = final_state.get("final_response") or ""
                            if not tokens_yielded and final_answer:
                                yield token_event(final_answer, trace_id).to_sse()
                                tokens_yielded = True
                            
                            # Fire widget event
                            tool_data = TOOL_DATA_CACHE.pop(trace_id, {})
                            parsed = parse_agent_result(tc, user_id, tool_data)
                            yield widget_event(
                                parsed["widgetId"], parsed["widgetParams"],
                                trace_id=trace_id, session_id=session_id
                            ).to_sse()
                            
                            # Fire done event
                            yield done_event(tc, trace_id, session_id).to_sse()
        except asyncio.CancelledError:
            yield cancelled_event(trace_id, session_id).to_sse()
            raise
        except Exception as e:
            logger.error("Streaming error: %s", e)
            yield error_event(str(e), trace_id, session_id).to_sse()

finance_agent = FinanceAgent()
