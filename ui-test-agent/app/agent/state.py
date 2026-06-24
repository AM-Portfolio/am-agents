import logging
from typing import Any, Dict, List, Optional, TypedDict


class AgentState(TypedDict):
    target_url: str
    specification: str
    steps: List[Dict[str, Any]]
    current_step_index: int
    selectors_db: Dict[str, str]
    failures_encountered: List[Dict[str, Any]]
    screenshot_history: List[str]
    screenshot_labels: List[str]
    report_output: Optional[str]
    mongodb_report_id: Optional[str]


class AutonomousAgentState(AgentState):
    testing_goal: str
    git_diff: Optional[str]
    visited_routes: List[str]
    action_log: List[Dict[str, Any]]
    visual_anomalies: List[str]
    design_review_results: List[Dict[str, Any]]
    design_review_summary: Dict[str, Any]
    baseline_mode: str
