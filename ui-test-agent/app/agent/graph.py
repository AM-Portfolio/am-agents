import logging

from langgraph.graph import END, StateGraph

from app.agent.assertions import assert_node
from app.agent.design_review import design_review_node
from app.agent.executor import executor_node
from app.agent.planner import planner_node
from app.agent.reporter import reporter_node
from app.agent.self_healer import self_heal_node
from app.agent.state import AutonomousAgentState
from app.config import settings

logger = logging.getLogger(__name__)


def _skip_self_heal(state: AutonomousAgentState) -> bool:
    steps = state.get("steps") or []
    return any(s.get("action") in ("click_demo_login", "wait_for_login") for s in steps)


def route_after_assert(state: AutonomousAgentState) -> str:
    idx = state.get("current_step_index", 0)
    steps = state.get("steps") or []
    failures = state.get("failures_encountered") or []

    if failures:
        if any(f.get("type") == "selector_not_found" for f in failures) and not _skip_self_heal(state):
            return "self_heal"
        return "report"

    if idx < len(steps):
        return "execute"

    if settings.DESIGN_REVIEW_ENABLED:
        return "design_review"
    return "report"


def route_after_plan(state: AutonomousAgentState) -> str:
    idx = state.get("current_step_index", 0)
    steps = state.get("steps") or []
    failures = state.get("failures_encountered") or []

    if failures:
        return "report"
    if idx < len(steps):
        return "execute"
    if settings.DESIGN_REVIEW_ENABLED:
        return "design_review"
    return "report"


workflow = StateGraph(AutonomousAgentState)

workflow.add_node("plan", planner_node)
workflow.add_node("execute", executor_node)
workflow.add_node("assert", assert_node)
workflow.add_node("design_review", design_review_node)
workflow.add_node("self_heal", self_heal_node)
workflow.add_node("report", reporter_node)

workflow.set_entry_point("plan")

workflow.add_conditional_edges(
    "plan",
    route_after_plan,
    {"execute": "execute", "design_review": "design_review", "report": "report"},
)
workflow.add_edge("execute", "assert")
workflow.add_conditional_edges(
    "assert",
    route_after_assert,
    {"execute": "execute", "self_heal": "self_heal", "design_review": "design_review", "report": "report"},
)
workflow.add_edge("self_heal", "execute")
workflow.add_edge("design_review", "report")
workflow.add_edge("report", END)

test_agent_graph = workflow.compile()
