"""In-memory fakes for contract tests and local development."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from am_platform_ports.schemas.core import (
    DirectoryHit,
    DocRef,
    InfraOpsAction,
    InfraOpsPlan,
    NotifyCard,
    TicketRef,
    TriageResult,
    WorkDoneResult,
)
from am_platform_ports.schemas.enums import RunKind, RunStatus, StepStatus
from am_platform_ports.schemas.run import AgentRun, AgentRunStep, CreateRunRequest, UpsertStepRequest


def _now() -> datetime:
    return datetime.now(UTC)


def _ref(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class FakeTriage:
    def classify(self, *, alert_payload: dict) -> TriageResult:
        return TriageResult(
            priority=str(alert_payload.get("priority", "P2")),
            category=str(alert_payload.get("category", "infra")),
            summary=str(alert_payload.get("summary", "alert")),
            labels={k: str(v) for k, v in (alert_payload.get("labels") or {}).items()},
        )


class FakeTicketStore:
    def __init__(self) -> None:
        self.tickets: dict[str, dict[str, Any]] = {}

    def create(self, *, title: str, description: str, priority: str, labels: dict[str, str] | None = None) -> TicketRef:
        ref = _ref("ticket")
        self.tickets[ref] = {
            "title": title,
            "description": description,
            "priority": priority,
            "labels": labels or {},
            "status": "open",
            "assignee_ref": None,
            "comments": [],
        }
        return TicketRef(ticket_ref=ref, url=f"fake://ticket/{ref}")

    def assign(self, *, ticket_ref: str, assignee_ref: str) -> None:
        self.tickets[ticket_ref]["assignee_ref"] = assignee_ref

    def comment(self, *, ticket_ref: str, body: str) -> None:
        self.tickets[ticket_ref]["comments"].append(body)

    def update_status(self, *, ticket_ref: str, status: str) -> None:
        self.tickets[ticket_ref]["status"] = status


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[str, NotifyCard]] = []

    def send_card(self, *, channel_ref: str, card: NotifyCard) -> str:
        self.sent.append((channel_ref, card))
        return _ref("notify")


class FakeDirectory:
    def resolve(self, *, labels: dict[str, str], priority: str) -> DirectoryHit:
        return DirectoryHit(assignee_ref="user:lab", team=labels.get("team", "lab"), channel_ref="cliq:lab")


class FakeMail:
    """In-memory mail; optionally dumps HTML/text under INCIDENT_MAIL_DUMP_DIR for E2E review."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def send(
        self,
        *,
        to: list[str],
        subject: str,
        body: str,
        refs: dict[str, str] | None = None,
        html_body: str | None = None,
    ) -> str:
        import os
        from pathlib import Path

        ref = _ref("mail")
        record = {
            "to": to,
            "subject": subject,
            "body": body,
            "html_body": html_body,
            "refs": refs or {},
            "mail_ref": ref,
        }
        self.sent.append(record)
        dump_dir = (os.getenv("INCIDENT_MAIL_DUMP_DIR") or "").strip()
        if dump_dir:
            out = Path(dump_dir)
            out.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            tid = str((refs or {}).get("tracking_id") or (refs or {}).get("ticket_ref") or ref)
            safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in tid)[:80]
            base = out / f"{stamp}_{safe}"
            (base.with_suffix(".txt")).write_text(
                f"To: {', '.join(to)}\nSubject: {subject}\n\n{body}",
                encoding="utf-8",
            )
            if html_body:
                (base.with_suffix(".html")).write_text(html_body, encoding="utf-8")
        return ref


class FakeCalendar:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def create_event(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
        attendees: list[str] | None = None,
        refs: dict[str, str] | None = None,
    ) -> str:
        ref = _ref("event")
        self.events.append(
            {
                "title": title,
                "start": start,
                "end": end,
                "attendees": attendees or [],
                "refs": refs or {},
                "event_ref": ref,
            }
        )
        return ref


class FakeDocStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(
        self,
        *,
        key: str,
        content: bytes,
        content_type: str = "application/octet-stream",
        meta: dict[str, str] | None = None,
    ) -> DocRef:
        _ = content_type, meta
        ref = f"fake:{key}"
        self.objects[ref] = content
        return DocRef(docs_ref=ref, provider="fake", url=f"fake://docs/{key}", key=key)

    def get(self, *, docs_ref: str) -> bytes:
        return self.objects[docs_ref]

    def exists(self, *, docs_ref: str) -> bool:
        return docs_ref in self.objects

    def browser_url(self, *, docs_ref: str, expires_seconds: int = 86400) -> str:
        _ = expires_seconds
        return f"https://docs.example.test/{docs_ref.removeprefix('fake:')}"


class FakePolicy:
    def allow(self, *, action: str, context: dict) -> bool:
        return True


class FakePromptRegistry:
    def __init__(self, prompts: dict[str, dict] | None = None) -> None:
        self._prompts = prompts or {
            "triage.default": {"system": "classify", "user": "{{summary}}"},
            "incident.analyze": {
                "system": "return json decision",
                "user": "Summary: {{summary}} Labels: {{labels}}",
            },
            "incident.ticket_update": {"system": "ticket comment", "user": "{{ticket_update}}"},
            "incident.resolution_note": {"system": "resolution", "user": "{{resolution_note}}"},
            "incident.escalate_unsolved": {
                "system": "handoff to human",
                "user": "Attempts: {{attempts}} Failure: {{failure_reason}}",
            },
        }

    def get(self, *, prompt_key: str, version: str | None = None) -> dict[str, Any]:
        _ = version
        return dict(self._prompts[prompt_key])


class FakeSecretBroker:
    def __init__(self, secrets: dict[str, str] | None = None) -> None:
        self._secrets = secrets or {}

    def resolve(self, *, secret_ref: str) -> str:
        if secret_ref not in self._secrets:
            raise KeyError(secret_ref)
        return self._secrets[secret_ref]


class FakeToolSandbox:
    """Deny-by-default allowlist for lab InfraOps + safe k8s."""

    ALLOWLIST = frozenset(
        {
            "lab.noop",
            "lab.mark_fixed",
            "lab.pod_status",
            "lab.pod_restart",
            "k8s.pod_status",
            "k8s.pod_describe",
            "k8s.rollout_restart",
        }
    )

    def run(self, *, tool_name: str, args: dict[str, Any], secret_refs: list[str] | None = None) -> dict[str, Any]:
        import os

        if tool_name not in self.ALLOWLIST:
            raise PermissionError(f"tool not allowlisted: {tool_name}")
        if os.getenv("INFRA_FORCE_FAIL", "").strip().lower() in {"1", "true", "yes", tool_name}:
            raise RuntimeError(f"forced infra failure for {tool_name}")
        return {"tool": tool_name, "ok": True, "args_keys": sorted(args.keys()), "secret_refs": secret_refs or []}


class FakeInfraOps:
    """Lab InfraOps — plans from decision actions or lab.mark_fixed; sandbox allowlist."""

    def __init__(self, sandbox: FakeToolSandbox | None = None, redactor: FakeRedactor | None = None) -> None:
        self._sandbox = sandbox or FakeToolSandbox()
        self._redactor = redactor or FakeRedactor()

    def plan(self, *, incident_ref: str, context: dict[str, Any]) -> InfraOpsPlan:
        proposed = context.get("proposed_actions") or []
        actions: list[InfraOpsAction] = []
        for item in proposed:
            if isinstance(item, dict):
                name = str(item.get("tool_name") or "")
                args = dict(item.get("args") or {})
            else:
                name = str(getattr(item, "tool_name", "") or "")
                args = dict(getattr(item, "args", None) or {})
            if name:
                actions.append(InfraOpsAction(tool_name=name, args=args))
        if not actions:
            actions = [
                InfraOpsAction(
                    tool_name="lab.mark_fixed",
                    args={"incident_ref": incident_ref, "ticket_ref": context.get("ticket_ref")},
                )
            ]
        return InfraOpsPlan(plan_ref=_ref("plan"), actions=actions)

    def execute(self, *, plan: InfraOpsPlan, secret_refs: list[str] | None = None) -> WorkDoneResult:
        ran: list[str] = []
        details: list[dict[str, Any]] = []
        for action in plan.actions:
            out = self._sandbox.run(
                tool_name=action.tool_name,
                args=action.args,
                secret_refs=secret_refs,
            )
            ran.append(action.tool_name)
            details.append(self._redactor.scrub(payload=out))
        summary = f"work_done actions={','.join(ran)}"
        return WorkDoneResult(
            work_ref=_ref("work"),
            plan_ref=plan.plan_ref,
            summary=summary,
            actions_ran=ran,
        )


class FakeRedactor:
    def scrub(self, *, payload: Any) -> Any:
        if isinstance(payload, dict):
            return {k: ("***" if "secret" in k.lower() or "token" in k.lower() else v) for k, v in payload.items()}
        return payload


class FakeLlm:
    """Deterministic LLM for CI — driven by ALERT_FORCE_DECISION env."""

    def complete(self, *, prompt_key: str, variables: dict[str, Any], data_class: str = "internal") -> str:
        import json
        import os

        _ = data_class
        if prompt_key == "incident.escalate_unsolved":
            return (
                "Agent could not finish. "
                f"Attempts: {variables.get('attempts')}. "
                f"Failure: {variables.get('failure_reason')}. "
                f"Verify: {variables.get('verify_status')}. "
                "Please investigate and apply a code/infra fix."
            )
        if prompt_key in {"incident.ticket_update", "incident.resolution_note"}:
            return str(variables.get("ticket_update") or variables.get("resolution_note") or variables.get("rationale") or "ok")

        force = os.getenv("ALERT_FORCE_DECISION", "needs_human").strip().lower()
        if force == "ignore":
            return json.dumps(
                {
                    "decision": "ignore",
                    "confidence": 0.95,
                    "rationale": "noise / not actionable",
                    "handoff_agent": None,
                    "proposed_actions": [],
                    "ticket_update": "Ignoring: not relevant to ops.",
                    "resolution_note": "Closed as ignore",
                }
            )
        if force == "auto_infra":
            return json.dumps(
                {
                    "decision": "auto_infra",
                    "confidence": 0.9,
                    "rationale": "pod may be down; safe restart",
                    "handoff_agent": "kagent_infra",
                    "proposed_actions": [
                        {"tool_name": "lab.pod_status", "args": {"target": "lab"}},
                        {"tool_name": "lab.pod_restart", "args": {"target": "lab"}},
                    ],
                    "ticket_update": "Auto infra: checking/restarting pod via kagent handoff.",
                    "resolution_note": "Pod checked/restarted; verify next.",
                }
            )
        if force == "delete_attempt":
            return json.dumps(
                {
                    "decision": "auto_infra",
                    "confidence": 0.99,
                    "rationale": "bad delete proposal",
                    "handoff_agent": "kagent_infra",
                    "proposed_actions": [{"tool_name": "k8s.delete_pod", "args": {}}],
                    "ticket_update": "should be blocked",
                    "resolution_note": "",
                }
            )
        return json.dumps(
            {
                "decision": "needs_human",
                "confidence": 0.85,
                "rationale": "likely application/code change required",
                "handoff_agent": None,
                "proposed_actions": [],
                "ticket_update": "Escalating: code/service change needed.",
                "resolution_note": "",
            }
        )


class FakeObservability:
    """
    Test ObservabilityPort only.

    VERIFY_FORCE_RESULT=passed|failed steers outcome when env is lab-allowed.
    When unset: fail closed (pass=False) so lab never auto-closes without real Prom.
    """

    def query(self, *, query_ref: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        import os

        from am_platform_ports.agent_identity import verify_force_allowed

        variables = variables or {}
        env = str(variables.get("env") or "lab").strip().lower() or "lab"
        force = os.getenv("VERIFY_FORCE_RESULT", "").strip().lower()
        if force and verify_force_allowed(env):
            failed = force in {"failed", "fail", "false", "0"}
            passed = not failed
        else:
            # No force (or force outside lab) → fail closed
            return {
                "pass": False,
                "query_ref": query_ref,
                "env": env,
                "error": "FakeObservability: set OBSERVE_PROVIDER=prometheus for live verify "
                "or VERIFY_FORCE_RESULT=passed|failed for unit tests only",
            }
        if "error_rate" in query_ref or query_ref.endswith("metrics") or "endpoints" in query_ref:
            if not passed:
                return {"value": 0.0, "threshold": 0.01, "pass": False, "query_ref": query_ref, "env": env}
            return {"value": 1.0, "threshold": 0.01, "pass": True, "query_ref": query_ref, "env": env}
        if not passed:
            return {"count": 5, "pass": False, "query_ref": query_ref, "env": env}
        return {"count": 0, "pass": True, "query_ref": query_ref, "env": env}


class FakeRunStore:
    """In-memory RunStore with claim/lease semantics for tests."""

    def __init__(self) -> None:
        self.runs: dict[str, AgentRun] = {}
        self.steps: dict[str, AgentRunStep] = {}

    def create_run(self, request: CreateRunRequest) -> AgentRun:
        now = _now()
        run = AgentRun(
            run_ref=_ref("run"),
            kind=request.kind,
            status=request.status,
            parent_run_ref=request.parent_run_ref,
            incident_ref=request.incident_ref,
            ticket_ref=request.ticket_ref,
            demand_ref=request.demand_ref,
            workflow_id=request.workflow_id,
            requested_selector_hash=request.requested_selector_hash,
            created_at=now,
            updated_at=now,
        )
        self.runs[run.run_ref] = run
        return run

    def get_run(self, *, run_ref: str) -> AgentRun | None:
        return self.runs.get(run_ref)

    def update_run_status(self, *, run_ref: str, status: RunStatus, summary: dict | None = None) -> AgentRun:
        run = self.runs[run_ref]
        updates: dict[str, Any] = {"status": status, "updated_at": _now()}
        if summary is not None:
            updates["summary"] = summary
            ticket_ref = summary.get("ticket_ref")
            if ticket_ref:
                updates["ticket_ref"] = str(ticket_ref)
        updated = run.model_copy(update=updates)
        self.runs[run_ref] = updated
        return updated

    def upsert_step(self, request: UpsertStepRequest) -> AgentRunStep:
        now = _now()
        existing = self.steps.get(request.step_ref)
        attempts = (existing.attempts if existing else 0) + (1 if request.bump_attempts else 0)
        step = AgentRunStep(
            step_ref=request.step_ref,
            run_ref=request.run_ref,
            name=request.name,
            check_ref=request.check_ref,
            status=request.status,
            worker_id=request.worker_id,
            attempts=attempts,
            last_error_class=request.last_error_class,
            result_ref=request.result_ref,
            created_at=existing.created_at if existing else now,
            updated_at=now,
            claim_lease_until=existing.claim_lease_until if existing else None,
        )
        self.steps[request.step_ref] = step
        if request.run_ref in self.runs and self.runs[request.run_ref].status in {
            RunStatus.ACCEPTED,
            RunStatus.PENDING,
        }:
            self.update_run_status(run_ref=request.run_ref, status=RunStatus.RUNNING)
        return step

    def list_steps(self, *, run_ref: str) -> list[AgentRunStep]:
        return [s for s in self.steps.values() if s.run_ref == run_ref]

    def claim_pending(
        self,
        *,
        worker_id: str,
        lease_until: datetime,
        limit: int = 1,
        name: str | None = None,
    ) -> list[AgentRunStep]:
        now = _now()
        claimed: list[AgentRunStep] = []
        for step in self.steps.values():
            if len(claimed) >= limit:
                break
            if name and step.name != name:
                continue
            lease_ok = step.claim_lease_until is None or step.claim_lease_until <= now
            if step.status == StepStatus.PENDING or (
                step.status == StepStatus.CLAIMED and lease_ok
            ):
                updated = step.model_copy(
                    update={
                        "status": StepStatus.CLAIMED,
                        "worker_id": worker_id,
                        "claim_lease_until": lease_until,
                        "attempts": step.attempts + 1,
                        "updated_at": now,
                    }
                )
                self.steps[step.step_ref] = updated
                claimed.append(updated)
        return claimed

    def heartbeat(self, *, step_ref: str, worker_id: str, lease_until: datetime) -> None:
        step = self.steps[step_ref]
        if step.worker_id != worker_id:
            raise PermissionError("worker mismatch")
        self.steps[step_ref] = step.model_copy(
            update={"claim_lease_until": lease_until, "updated_at": _now()}
        )

    def complete_step(
        self,
        *,
        step_ref: str,
        status: str,
        result_ref: str | None = None,
        error_class: str | None = None,
    ) -> AgentRunStep:
        from am_platform_ports.schemas.enums import ErrorClass

        step = self.steps[step_ref]
        updated = step.model_copy(
            update={
                "status": StepStatus(status),
                "result_ref": result_ref,
                "last_error_class": ErrorClass(error_class) if error_class else None,
                "updated_at": _now(),
            }
        )
        self.steps[step_ref] = updated
        return updated


class FakeHandoff:
    """In-memory handoff — max depth 1; creates RunKind.HANDOFF via RunStore."""

    MAX_DEPTH = 1

    def __init__(self, runs: FakeRunStore | None = None) -> None:
        self._runs = runs or FakeRunStore()
        self.handoffs: list[dict[str, Any]] = []

    def handoff(
        self,
        *,
        from_run_ref: str,
        to_kind: str,
        depth: int,
        context: dict[str, Any] | None = None,
    ) -> str:
        if depth > self.MAX_DEPTH:
            raise PermissionError(f"handoff depth {depth} exceeds MAX_DEPTH={self.MAX_DEPTH}")
        if depth < 0:
            raise ValueError("handoff depth must be >= 0")
        parent = self._runs.get_run(run_ref=from_run_ref)
        if parent is None:
            raise KeyError(f"unknown from_run_ref: {from_run_ref}")
        try:
            kind = RunKind(to_kind)
        except ValueError as exc:
            raise ValueError(f"invalid to_kind: {to_kind}") from exc
        run = self._runs.create_run(
            CreateRunRequest(
                kind=RunKind.HANDOFF,
                status=RunStatus.ACCEPTED,
                parent_run_ref=from_run_ref,
                incident_ref=parent.incident_ref,
                demand_ref=parent.demand_ref,
                workflow_id=parent.workflow_id,
            )
        )
        self._runs.update_run_status(
            run_ref=run.run_ref,
            status=RunStatus.ACCEPTED,
            summary={"to_kind": kind.value, "depth": depth, "context": context or {}},
        )
        self.handoffs.append(
            {
                "from_run_ref": from_run_ref,
                "to_kind": kind.value,
                "depth": depth,
                "run_ref": run.run_ref,
            }
        )
        return run.run_ref
