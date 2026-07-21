from __future__ import annotations

import importlib
import os
from typing import Any

from app.models.intent import IntentDocument
from tools._base_plugin import BaseIntegrationTool
from tools._shared.capability.approval import requires_write_confirmation, risk_for_operation
from tools._shared.capability.errors import CapabilityError, classify_error
from tools._shared.capability.idempotency import get_idempotency_store
from tools._shared.capability.plan_binding import intent_plan_hash
from tools._shared.capability.results import normalize_result


class CapabilityTool(BaseIntegrationTool):
    """Generic capability plugin: env-gated enable + provider-selected adapter."""

    provider_env: str = ""
    default_provider: str = "memory"
    allowed_providers: frozenset[str] = frozenset({"memory"})

    def _pkg(self) -> str:
        return f"tools.{self._tool_dir.name}"

    def is_enabled(self) -> bool:
        if self._manifest.enabled:
            return True
        allow = os.environ.get("TOOL_AGENT_CAPABILITY_PLUGINS", "")
        names = {x.strip() for x in allow.split(",") if x.strip()}
        return self.name in names or self._tool_dir.name in names

    def provider_name(self) -> str:
        from tools._shared.capability.provider import resolve_provider

        return resolve_provider(
            env_var=self.provider_env,
            default=self.default_provider,
            allowed=self.allowed_providers,
        )

    def build_adapter(self, provider: str) -> Any:
        raise NotImplementedError

    def parse_rules(self, query: str, backend_hint: str | None) -> IntentDocument | None:
        if backend_hint and backend_hint != self.name:
            return None
        mod = importlib.import_module(f"{self._pkg()}.search.parse_rules")
        return mod.parse_rules(query, tool_name=self.name, backend_hint=backend_hint)

    def resolve(self, intent: IntentDocument, query: str) -> tuple[IntentDocument, str | None]:
        mod = importlib.import_module(f"{self._pkg()}.search.resolve")
        return mod.resolve(intent, query)

    def validate_safety(self, intent: IntentDocument, *, request_read_only: bool) -> None:
        mod = importlib.import_module(f"{self._pkg()}.safety")
        mod.validate(intent, request_read_only=request_read_only)

    def adapter_available(self) -> bool:
        try:
            adapter = self.build_adapter(self.provider_name())
        except Exception:
            return False
        return bool(getattr(adapter, "available", True))

    def _approval_risk(self, operation: str) -> str:
        op_cfg = (self.registry_entry().get("operations") or {}).get(operation) or {}
        return risk_for_operation(operation, op_cfg)

    async def execute(self, intent: IntentDocument, *, read_only: bool, max_rows: int) -> Any:
        _ = max_rows
        safety = importlib.import_module(f"{self._pkg()}.safety")
        safety.validate_tool_params(intent.operation, intent.params)
        provider = self.provider_name()
        adapter = self.build_adapter(provider)
        if not getattr(adapter, "available", True):
            raise CapabilityError(f"provider {provider!r} unavailable for {self.name}", error_class="fatal")

        capability = f"{self.name}.{intent.operation}"
        risk = self._approval_risk(intent.operation)
        plan_hash = intent_plan_hash(intent)
        idem_key = None
        if isinstance(intent.params, dict):
            idem_key = intent.params.get("idempotency_key") or intent.params.get("idempotencyKey")
        store = get_idempotency_store()
        if idem_key and requires_write_confirmation(risk):  # type: ignore[arg-type]
            cached = store.get(str(idem_key), plan_hash=plan_hash)
            if cached is not None:
                return cached

        try:
            data = await adapter.execute(intent.operation, dict(intent.params), read_only=read_only)
            result = normalize_result(
                capability=capability,
                provider=provider,
                data=data if isinstance(data, dict) else {"value": data},
                approval_risk=risk,
                idempotency_key=str(idem_key) if idem_key else None,
                async_operation_ref=(data or {}).get("async_operation_ref") if isinstance(data, dict) else None,
            )
        except Exception as exc:
            raise CapabilityError(str(exc), error_class=classify_error(exc)) from exc

        if idem_key and requires_write_confirmation(risk):  # type: ignore[arg-type]
            store.put(str(idem_key), plan_hash=plan_hash, result=result)
        return result
