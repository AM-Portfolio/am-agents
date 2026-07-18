"""SPT request/result schemas (stubs until Phase 3 adapters)."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from am_platform_ports.schemas.enums import ErrorClass, FailureMode


class SptSelector(BaseModel):
    ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    all: bool = False

    @model_validator(mode="after")
    def _require_selector(self) -> "SptSelector":
        if self.all:
            return self
        if not self.ids and not self.tags:
            raise ValueError("empty selector is fatal — provide ids and/or tags (never default-all)")
        return self


class SptDemandRequest(BaseModel):
    demand_ref: str
    selector: SptSelector
    parallelism: int = 2
    failure_mode: FailureMode = FailureMode.CONTINUE
    env: Literal["lab", "prod"] = "lab"


class ChildRunResult(BaseModel):
    target_ref: str
    status: Literal["succeeded", "failed", "skipped", "cancelled"]
    error_class: ErrorClass | None = None
    load_run_ref: str | None = None
    observe_ref: str | None = None
    duration_ms: int | None = None


class SptRunSummary(BaseModel):
    run_id: str
    requested_count: int = 0
    ran_count: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    cancelled: int = 0
    children: list[ChildRunResult] = Field(default_factory=list)
    docs_ref: str | None = None
    overall_status: Literal["succeeded", "partial", "failed"] = "failed"
