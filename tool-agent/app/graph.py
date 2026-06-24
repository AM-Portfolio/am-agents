from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.nodes.check_intent_policy import check_intent_policy_node
from app.nodes.execute_tool import resolve_and_execute_node
from app.nodes.format_response import format_response_node
from app.nodes.parse_intent import parse_intent_node
from app.nodes.resolve_params import resolve_params_node
from app.nodes.validate_safety import validate_safety_node
from app.state import ToolAgentState


def _route_on_error(state: ToolAgentState) -> str:
    if state.get("error"):
        return "end"
    return "continue"


workflow = StateGraph(ToolAgentState)

workflow.add_node("parse_intent", parse_intent_node)
workflow.add_node("resolve_params", resolve_params_node)
workflow.add_node("validate_safety", validate_safety_node)
workflow.add_node("check_intent_policy", check_intent_policy_node)
workflow.add_node("execute_tool", resolve_and_execute_node)
workflow.add_node("format_response", format_response_node)

workflow.set_entry_point("parse_intent")

workflow.add_conditional_edges("parse_intent", _route_on_error, {"continue": "resolve_params", "end": END})
workflow.add_conditional_edges("resolve_params", _route_on_error, {"continue": "validate_safety", "end": END})
workflow.add_conditional_edges("validate_safety", _route_on_error, {"continue": "check_intent_policy", "end": END})
workflow.add_conditional_edges("check_intent_policy", _route_on_error, {"continue": "execute_tool", "end": END})
workflow.add_conditional_edges("execute_tool", _route_on_error, {"continue": "format_response", "end": END})
workflow.add_edge("format_response", END)

tool_agent_graph = workflow.compile()
