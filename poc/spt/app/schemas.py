from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Audience = Literal["developer", "agent", "ci", "shared"]


class PayloadBundle(BaseModel):
    k6_import: dict[str, Any] = Field(default_factory=dict)
    playwright_import: dict[str, Any] = Field(default_factory=dict)
    bench_run: dict[str, Any] = Field(default_factory=dict)
    har_stub: dict[str, Any] | None = None
    api_overrides: list[dict[str, Any]] = Field(default_factory=list)
    auth_env: dict[str, Any] = Field(default_factory=dict)
    payload_set_version: int | None = None


class TestConfigIn(BaseModel):
    name: str = "default-smoke"
    description: str = ""
    service: str = "am-core-services"
    environment: str = "dev"
    openapi_version: str | None = None  # OpenAPI info.version pin for load-test catalog
    test_type: Literal["k6", "playwright", "mixed"] = "k6"
    target_url: str | None = None
    run_profile: Literal["debug", "load"] | None = None
    audience: Audience = "developer"
    payload_set_version: int | None = None
    selected_api_ids: list[str] | None = None
    payloads: PayloadBundle = Field(default_factory=PayloadBundle)
    scripts: dict[str, str] = Field(default_factory=dict)


class TestConfigUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    service: str | None = None
    environment: str | None = None
    openapi_version: str | None = None
    test_type: str | None = None
    target_url: str | None = None
    run_profile: Literal["debug", "load"] | None = None
    audience: Audience | None = None
    payload_set_version: int | None = None
    selected_api_ids: list[str] | None = None
    payloads: PayloadBundle | None = None
    scripts: dict[str, str] | None = None


class RunExecuteRequest(BaseModel):
    config_id: str | None = None
    config: TestConfigIn | None = None
    save_config: bool = False
    triggered_by: str = "manual"
    preset: str | None = None  # smoke | load | 20u-50 | stress
    profile: Literal["debug", "load"] | None = None
    vus: int | None = None
    iterations: int | None = None  # total shared calls across VUs
    duration: str | None = None
    wait: bool = False  # True = block until finished (CLI); UI uses async (default)
    payload_refs: list[dict[str, Any]] = Field(default_factory=list)
    # each: {api_id, name?, version?} OR use payload_set_version for whole service set
    payload_set_version: int | None = None
    api_ids: list[str] | None = None  # subset of catalog APIs; None/empty = all
    environment: str | None = None  # override config env for this run (API version source)
    openapi_version: str | None = None  # record/pin OpenAPI info.version for this run
    # Resolve profile when config_id is omitted (agents): service + audience
    service: str | None = None
    audience: Audience | None = None


class SavePayloadRequest(BaseModel):
    name: str = "default"
    service: str | None = None


class PayloadCreateRequest(BaseModel):
    service: str
    api_id: str
    name: str = "default"
    request: dict[str, Any] = Field(default_factory=dict)
    response: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)
    source_run_id: str | None = None
    bump: bool = True
    # Service-level set: register this API into set version (None = active set)
    set_version: int | None = None
    bump_set: bool = False  # clone set to new service version before writing
    into_set: bool = True  # also upsert into service payload set


class PayloadSetCreateRequest(BaseModel):
    service: str
    label: str | None = None
    clone_from: int | None = None
    make_active: bool = True


class PayloadSetUpsertApiRequest(BaseModel):
    service: str
    api_id: str
    version: int | None = None
    name: str = "working"
    request: dict[str, Any] = Field(default_factory=dict)
    response: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)
    bump_set: bool = False


class RunFilterQuery(BaseModel):
    service: str | None = None
    environment: str | None = None
    status: str | None = None
    config_name: str | None = None
    test_type: str | None = None
    triggered_by: str | None = None
    q: str | None = None
    limit: int = 100
