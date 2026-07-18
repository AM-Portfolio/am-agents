"""Small dependency-free, low-cardinality Prometheus metrics registry."""

from __future__ import annotations

import threading
from collections import Counter

from am_support_agent.contracts.enums import SupportDomain, TaskStatus
from am_support_agent.contracts.schemas import TaskRequest, TaskResult

_LATENCY_BUCKETS = (
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
    60.0,
)
_ERROR_TYPES = {
    "adapter_error",
    "agent_mismatch",
    "execute_failed",
    "http_error",
    "idempotency_required",
    "no_adapter",
    "plan_failed",
    "status_failed",
    "timeout",
    "unhealthy",
    "unknown_task",
    "unsupported_op",
}


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class Metrics:
    def __init__(self, *, application: str = "support-agent") -> None:
        self.application = application
        self._requests: Counter[tuple[str, str, str]] = Counter()
        self._latency_count: Counter[tuple[str, str]] = Counter()
        self._latency_sum: Counter[tuple[str, str]] = Counter()
        self._latency_buckets: Counter[tuple[str, str, float]] = Counter()
        self._events: Counter[tuple[str, str, str]] = Counter()
        self._business_requests: Counter[str] = Counter()
        self._outcomes: Counter[tuple[str, str]] = Counter()
        self._automation: Counter[tuple[str, str]] = Counter()
        self._hitl: Counter[str] = Counter()
        self._parity: Counter[tuple[str, str]] = Counter()
        self._canary: Counter[tuple[str, str]] = Counter()
        self._memory: Counter[tuple[str, str]] = Counter()
        self._learning: Counter[str] = Counter()
        self._in_flight: Counter[tuple[str, str]] = Counter()
        self._run_store_healthy = 0
        self._episode_store_healthy = 0
        self._feedback_store_healthy = 0
        self._lock = threading.Lock()

    def task_started(self, request: TaskRequest) -> None:
        with self._lock:
            self._in_flight[(request.op.value, request.agent_id)] += 1

    def observe(self, request: TaskRequest, result: TaskResult) -> None:
        op = request.op.value
        agent = result.agent_id
        domain = request.business_domain.value
        latency = max(0.0, result.metrics.latency_ms / 1000)
        with self._lock:
            self._in_flight[(op, request.agent_id)] = max(
                0, self._in_flight[(op, request.agent_id)] - 1
            )
            self._requests[(op, agent, result.status.value)] += 1
            self._latency_count[(op, agent)] += 1
            self._latency_sum[(op, agent)] += latency
            for bucket in _LATENCY_BUCKETS:
                if latency <= bucket:
                    self._latency_buckets[(op, agent, bucket)] += 1
            if result.error is not None:
                error_type = (
                    result.error.code if result.error.code in _ERROR_TYPES else "other"
                )
                self._events[("error", op, error_type)] += 1
            if result.status == TaskStatus.TIMED_OUT:
                self._events[("timeout", op, agent)] += 1
            if result.status == TaskStatus.CANCELLED:
                self._events[("cancelled", op, agent)] += 1
            self._business_requests[domain] += 1
            self._outcomes[(domain, _resolution_outcome(result.status))] += 1
            mode = "human_needed" if request.requires_human else "automated"
            self._automation[(domain, mode)] += 1
            if request.requires_human:
                self._hitl[domain] += 1

    def idempotency_hit(self, request: TaskRequest) -> None:
        with self._lock:
            self._events[("idempotency_hit", request.op.value, request.agent_id)] += 1

    def task_aborted(self, request: TaskRequest) -> None:
        """Close an in-flight gauge and count an unexpected internal error."""
        with self._lock:
            key = (request.op.value, request.agent_id)
            self._in_flight[key] = max(0, self._in_flight[key] - 1)
            self._events[("error", request.op.value, "unhandled")] += 1

    def set_run_store_health(self, healthy: bool) -> None:
        with self._lock:
            self._run_store_healthy = int(healthy)

    def observe_parity(self, domain: SupportDomain, matched: bool) -> None:
        with self._lock:
            self._parity[(domain.value, "pass" if matched else "fail")] += 1

    def observe_canary(self, *, mode: str, route: str) -> None:
        with self._lock:
            self._canary[(mode or "off", route or "legacy")] += 1

    def observe_episode(self, *, result: str) -> None:
        """result: write | conflict | outcome | failure"""
        with self._lock:
            self._memory[("episode", result or "unknown")] += 1

    def observe_feedback(self, *, result: str) -> None:
        """result: write | conflict | failure"""
        with self._lock:
            self._memory[("feedback", result or "unknown")] += 1

    def observe_retrieval(self, *, result: str) -> None:
        """result: hit | empty | skipped"""
        with self._lock:
            self._memory[("retrieval", result or "unknown")] += 1

    def observe_learning(self, *, kind: str) -> None:
        """kind: evaluation | candidate | promotion_allowed | promotion_blocked"""
        with self._lock:
            self._learning[kind or "unknown"] += 1

    def set_episode_store_health(self, healthy: bool) -> None:
        with self._lock:
            self._episode_store_healthy = int(healthy)

    def set_feedback_store_health(self, healthy: bool) -> None:
        with self._lock:
            self._feedback_store_healthy = int(healthy)

    def render(self) -> str:
        application = f'application="{_escape(self.application)}"'
        lines = [
            "# HELP support_agent_a2a_requests_total A2A task results.",
            "# TYPE support_agent_a2a_requests_total counter",
        ]
        with self._lock:
            for (op, agent, status), count in sorted(self._requests.items()):
                labels = (
                    f'{application},op="{_escape(op)}",agent="{_escape(agent)}",'
                    f'status="{_escape(status)}"'
                )
                lines.append(
                    f"support_agent_a2a_requests_total{{{labels}}} {count}"
                )
            lines.extend(
                [
                    "# HELP support_agent_adapter_latency_seconds Specialist adapter latency.",
                    "# TYPE support_agent_adapter_latency_seconds histogram",
                ]
            )
            for (op, agent), count in sorted(self._latency_count.items()):
                labels = f'{application},op="{_escape(op)}",agent="{_escape(agent)}"'
                for bucket in _LATENCY_BUCKETS:
                    bucket_count = self._latency_buckets[(op, agent, bucket)]
                    lines.append(
                        "support_agent_adapter_latency_seconds_bucket"
                        f'{{{labels},le="{bucket:g}"}} {bucket_count}'
                    )
                lines.append(
                    "support_agent_adapter_latency_seconds_bucket"
                    f'{{{labels},le="+Inf"}} {count}'
                )
                lines.append(
                    f"support_agent_adapter_latency_seconds_sum{{{labels}}} "
                    f"{self._latency_sum[(op, agent)]:g}"
                )
                lines.append(
                    f"support_agent_adapter_latency_seconds_count{{{labels}}} {count}"
                )
            lines.extend(self._render_events(application))
            lines.extend(
                [
                    "# HELP support_agent_in_flight_tasks Current executing tasks.",
                    "# TYPE support_agent_in_flight_tasks gauge",
                ]
            )
            for (op, agent), value in sorted(self._in_flight.items()):
                lines.append(
                    "support_agent_in_flight_tasks"
                    f'{{{application},op="{_escape(op)}",'
                    f'agent="{_escape(agent)}"}} {value}'
                )
            lines.extend(
                [
                    "# HELP support_agent_run_store_healthy Run-store readiness (1 healthy).",
                    "# TYPE support_agent_run_store_healthy gauge",
                    "support_agent_run_store_healthy"
                    f"{{{application}}} {self._run_store_healthy}",
                    "# HELP support_agent_business_requests_total Requests by allowlisted domain.",
                    "# TYPE support_agent_business_requests_total counter",
                ]
            )
            for domain, count in sorted(self._business_requests.items()):
                lines.append(
                    "support_agent_business_requests_total"
                    f'{{{application},domain="{domain}"}} {count}'
                )
            lines.extend(
                [
                    "# HELP support_agent_resolution_outcomes_total Resolution outcomes.",
                    "# TYPE support_agent_resolution_outcomes_total counter",
                ]
            )
            for (domain, outcome), count in sorted(self._outcomes.items()):
                lines.append(
                    "support_agent_resolution_outcomes_total"
                    f'{{{application},domain="{domain}",outcome="{outcome}"}} {count}'
                )
            lines.extend(
                [
                    "# HELP support_agent_automation_total Automated versus human-needed requests.",
                    "# TYPE support_agent_automation_total counter",
                ]
            )
            for (domain, mode), count in sorted(self._automation.items()):
                lines.append(
                    "support_agent_automation_total"
                    f'{{{application},domain="{domain}",mode="{mode}"}} {count}'
                )
            lines.extend(
                [
                    "# HELP support_agent_hitl_total Requests requiring human intervention.",
                    "# TYPE support_agent_hitl_total counter",
                ]
            )
            for domain, count in sorted(self._hitl.items()):
                lines.append(
                    f'support_agent_hitl_total{{{application},domain="{domain}"}} '
                    f"{count}"
                )
            lines.extend(
                [
                    "# HELP support_agent_shadow_parity_total Shadow parity results.",
                    "# TYPE support_agent_shadow_parity_total counter",
                ]
            )
            for (domain, result), count in sorted(self._parity.items()):
                lines.append(
                    "support_agent_shadow_parity_total"
                    f'{{{application},domain="{domain}",result="{result}"}} {count}'
                )
            lines.extend(
                [
                    "# HELP support_agent_canary_route_total Canary route decisions.",
                    "# TYPE support_agent_canary_route_total counter",
                ]
            )
            for (mode, route), count in sorted(self._canary.items()):
                lines.append(
                    "support_agent_canary_route_total"
                    f'{{{application},mode="{_escape(mode)}",route="{_escape(route)}"}} '
                    f"{count}"
                )
            lines.extend(
                [
                    "# HELP support_agent_memory_events_total Episode/feedback/retrieval events.",
                    "# TYPE support_agent_memory_events_total counter",
                ]
            )
            for (kind, result), count in sorted(self._memory.items()):
                lines.append(
                    "support_agent_memory_events_total"
                    f'{{{application},kind="{_escape(kind)}",result="{_escape(result)}"}} '
                    f"{count}"
                )
            lines.extend(
                [
                    "# HELP support_agent_learning_events_total Offline learning pipeline events.",
                    "# TYPE support_agent_learning_events_total counter",
                ]
            )
            for kind, count in sorted(self._learning.items()):
                lines.append(
                    "support_agent_learning_events_total"
                    f'{{{application},kind="{_escape(kind)}"}} {count}'
                )
            lines.extend(
                [
                    "# HELP support_agent_episode_store_healthy Episode store readiness (1 healthy).",
                    "# TYPE support_agent_episode_store_healthy gauge",
                    "support_agent_episode_store_healthy"
                    f"{{{application}}} {self._episode_store_healthy}",
                    "# HELP support_agent_feedback_store_healthy Feedback store readiness (1 healthy).",
                    "# TYPE support_agent_feedback_store_healthy gauge",
                    "support_agent_feedback_store_healthy"
                    f"{{{application}}} {self._feedback_store_healthy}",
                ]
            )
        return "\n".join(lines) + "\n"

    def _render_events(self, application: str) -> list[str]:
        definitions = {
            "error": ("support_agent_errors_total", "Task errors.", "error_type"),
            "timeout": ("support_agent_timeouts_total", "Timed-out tasks.", "agent"),
            "cancelled": ("support_agent_cancelled_total", "Cancelled tasks.", "agent"),
            "idempotency_hit": (
                "support_agent_idempotency_hits_total",
                "Durable idempotency cache hits.",
                "agent",
            ),
        }
        lines: list[str] = []
        for event, (name, help_text, third_label) in definitions.items():
            lines.extend([f"# HELP {name} {help_text}", f"# TYPE {name} counter"])
            for (kind, op, third), count in sorted(self._events.items()):
                if kind == event:
                    lines.append(
                        f'{name}{{{application},op="{_escape(op)}",'
                        f'{third_label}="{_escape(third)}"}} {count}'
                    )
        return lines


def _resolution_outcome(status: TaskStatus) -> str:
    if status == TaskStatus.SUCCEEDED:
        return "resolved"
    if status == TaskStatus.CANCELLED:
        return "cancelled"
    if status == TaskStatus.TIMED_OUT:
        return "timed_out"
    if status in {TaskStatus.ACCEPTED, TaskStatus.RUNNING}:
        return "pending"
    return "failed"
