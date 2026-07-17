"""RunStore — ops ledger + claim queue (ADR-005)."""

from datetime import datetime
from typing import Protocol, runtime_checkable

from am_platform_ports.schemas.enums import RunStatus
from am_platform_ports.schemas.run import AgentRun, AgentRunStep, CreateRunRequest, UpsertStepRequest


@runtime_checkable
class RunStore(Protocol):
    def create_run(self, request: CreateRunRequest) -> AgentRun:
        """Intake: always write initial status before heavy work."""
        ...

    def get_run(self, *, run_ref: str) -> AgentRun | None: ...

    def update_run_status(self, *, run_ref: str, status: RunStatus, summary: dict | None = None) -> AgentRun: ...

    def upsert_step(self, request: UpsertStepRequest) -> AgentRunStep: ...

    def list_steps(self, *, run_ref: str) -> list[AgentRunStep]: ...

    def claim_pending(
        self,
        *,
        worker_id: str,
        lease_until: datetime,
        limit: int = 1,
        name: str | None = None,
    ) -> list[AgentRunStep]:
        """Claim pending (or expired-lease) steps — SKIP LOCKED semantics in Postgres adapter."""
        ...

    def heartbeat(self, *, step_ref: str, worker_id: str, lease_until: datetime) -> None: ...

    def complete_step(
        self,
        *,
        step_ref: str,
        status: str,
        result_ref: str | None = None,
        error_class: str | None = None,
    ) -> AgentRunStep: ...
