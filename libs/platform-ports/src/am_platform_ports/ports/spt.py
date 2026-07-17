"""Phase 2/3 port stubs — full adapters later."""

from typing import Any, Protocol, runtime_checkable

from am_platform_ports.schemas.spt import SptDemandRequest, SptSelector


@runtime_checkable
class ObservabilityPort(Protocol):
    def query(self, *, query_ref: str, variables: dict[str, Any] | None = None) -> dict[str, Any]: ...


@runtime_checkable
class TargetCatalog(Protocol):
    def list_services(self) -> list[dict[str, Any]]: ...

    def get(self, *, target_id: str) -> dict[str, Any] | None: ...


@runtime_checkable
class TargetResolver(Protocol):
    def resolve(self, *, selector: SptSelector) -> list[str]:
        """Expand selector to target ids. Empty selector must already be rejected by schema."""
        ...


@runtime_checkable
class LoadPolicy(Protocol):
    def allow(self, *, target_ref: str, request: SptDemandRequest) -> bool: ...


@runtime_checkable
class LoadTestRunner(Protocol):
    def run(
        self,
        *,
        scenario_ref: str,
        base_url_secret_ref: str,
        dataset_ref: str | None = None,
        target_ref: str | None = None,
    ) -> str:
        """Return opaque load_run_ref. Execute via ToolSandbox."""
        ...


@runtime_checkable
class DataPrep(Protocol):
    def ensure_dataset(self, *, prep_ref: str, parent_run_ref: str | None = None) -> str:
        """Return dataset_ref. Dedupe once per distinct prep_ref per parent run."""
        ...
