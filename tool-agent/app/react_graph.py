from __future__ import annotations

import json
import logging
from typing import Any

from langgraph.graph import END, StateGraph

from app.llm_client import get_llm_client
from app.models.intent import IntentDocument, ReactHistoryItem
from app.nodes.execute_tool import resolve_and_execute_node
from app.prompts.react import build_react_prompt
from app.schema.loader import get_schema_catalog
from app.state import ReactAgentState

logger = logging.getLogger(__name__)

async def agent_reason_node(state: ReactAgentState) -> ReactAgentState:
    if state.get("error"):
        return state

    loop_count = state.get("loop_count", 0)
    if loop_count >= state["request"].max_loops:
        return {**state, "final_answer": "Max loops reached without resolution."}

    llm = get_llm_client()
    catalog = get_schema_catalog()
    
    # Format history
    history_list = state.get("history", [])
    history_str = json.dumps([
        {
            "action": {"backend": h.action.backend, "operation": h.action.operation, "params": h.action.params},
            "result": h.result.data if h.result and h.result.ok else (h.result.error if h.result else None)
        } for h in history_list
    ], indent=2)

    system_prompt = build_react_prompt(
        history=history_str,
        catalog=catalog,
        backends=[state["request"].backend] if state["request"].backend else None
    )

    user_msg = f"User Request: {state['query']}"

    try:
        res = await llm.chat_with_usage(
            system=system_prompt,
            user=user_msg,
            request_id=state["request_id"],
            generation_name="tool_agent.react",
        )
        
        text = (res.content or "").strip()
        # Parse JSON
        import re
        # Try to find JSON block first
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if match:
            text = match.group(1)
        else:
            # Fallback: extract substring from first { to last }
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                text = text[start:end+1]

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            print(f"\n[DEBUG] LLM RAW OUTPUT:\n{res.content}\n")
            return {**state, "error": f"Failed to parse reasoning: {e}"}
        
        if "answer" in data:
            return {**state, "final_answer": data["answer"]}
        elif "action" in data:
            action = data["action"]
            intent = IntentDocument(
                backend=action.get("backend", ""),
                operation=action.get("operation", ""),
                params=action.get("params", {}),
                read_only=state["request"].read_only,
                confidence=1.0,
                rationale=data.get("reasoning", "ReAct Loop")
            )
            return {**state, "intent": intent, "loop_count": loop_count + 1}
        else:
            return {**state, "error": "LLM returned invalid JSON structure (missing action or answer)"}

    except Exception as e:
        return {**state, "error": f"Failed to parse reasoning: {e}"}


async def execute_tool_node(state: ReactAgentState) -> ReactAgentState:
    if state.get("error"):
        return state
        
    if not state.get("intent"):
        return state

    # Wrap the intent execution
    # We create a dummy ToolAgentState since resolve_and_execute_node expects it
    from app.state import ToolAgentState
    from app.models.intent import ToolsQueryRequest
    dummy_req = ToolsQueryRequest(query=state["query"], max_rows=100)
    
    execute_state: ToolAgentState = {
        "request": dummy_req,
        "request_id": state["request_id"],
        "intent": state["intent"]
    }
    
    result_state = await resolve_and_execute_node(execute_state)
    
    if result_state.get("error"):
        # Wrap error in tool result
        from app.models.intent import ToolResult
        tool_res = ToolResult(ok=False, error=result_state["error"], tool_source="adapter", tool_name=state["intent"].operation)
    else:
        tool_res = result_state.get("tool_result")

    # Append to history
    history = state.get("history", [])
    history.append(ReactHistoryItem(action=state["intent"], result=tool_res))
    
    # Clear intent for next loop
    new_state = {**state, "history": history, "tool_result": tool_res}
    new_state.pop("intent", None)
    return new_state


def _route_after_reason(state: ReactAgentState) -> str:
    if state.get("error") or state.get("final_answer"):
        return "end"
    if state.get("intent"):
        return "execute"
    return "end"


workflow = StateGraph(ReactAgentState)

workflow.add_node("agent_reason", agent_reason_node)
workflow.add_node("execute_tool", execute_tool_node)

workflow.set_entry_point("agent_reason")

workflow.add_conditional_edges("agent_reason", _route_after_reason, {"execute": "execute_tool", "end": END})
workflow.add_edge("execute_tool", "agent_reason")

react_graph = workflow.compile()
