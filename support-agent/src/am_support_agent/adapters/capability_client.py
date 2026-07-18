"""Capability client over tool-agent plan/execute (generic capability IDs)."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

import httpx

from am_support_agent.contracts.capabilities import CapabilityCall
from am_support_agent.observability.tracing import inject_trace_headers
from am_support_agent.ports.capability import CapabilityResult


def _split_capability(capability: str) -> tuple[str, str]:
    """Map `work-item.create` → backend `work-item`, operation `create`."""
    raw = (capability or "").strip()
    if "." not in raw:
        raise ValueError(f"capability must be backend.operation, got {capability!r}")
    backend, operation = raw.split(".", 1)
    if not backend or not operation:
        raise ValueError(f"invalid capability {capability!r}")
    return backend, operation


def _plan_hash(intent: dict[str, Any]) -> str:
    raw = json.dumps(intent, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


class ToolAgentCapabilityClient:
    name = "tool-agent"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = (
            base_url
            or os.getenv("TOOL_AGENT_BASE_URL", "").strip()
            or os.getenv("SUPPORT_AGENT_TOOL_AGENT_URL", "").strip()
            or "http://127.0.0.1:8141"
        ).rstrip("/")
        self._client = client
        self._owns_client = client is None

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "wired": True,
            "base_url": self.base_url,
            "transport": "http+/api/v1/tools/plan|execute",
        }

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def call(self, call: CapabilityCall) -> CapabilityResult:
        backend, operation = _split_capability(call.capability)
        params = dict(call.args)
        if call.idempotency:
            params.setdefault("idempotency_key", call.idempotency.key)
        intent = {
            "backend": backend,
            "operation": operation,
            "params": params,
            "read_only": call.approval.risk.value == "read",
            "confidence": 1.0,
            "rationale": "support-agent capability call",
        }
        if call.provider_hint:
            intent["params"]["_provider_hint"] = call.provider_hint

        plan_hash = (
            call.idempotency.plan_hash
            if call.idempotency and call.idempotency.plan_hash
            else _plan_hash(intent)
        )
        client = await self._http()
        headers: dict[str, str] = {"Accept": "application/json", "Content-Type": "application/json"}
        inject_trace_headers(headers)
        if call.idempotency:
            headers["Idempotency-Key"] = call.idempotency.key

        # Prefer structured execute; if writes need confirmation, plan first.
        execute_body: dict[str, Any] = {
            "intent": intent,
            "include_summary": False,
            "plan_hash": plan_hash,
        }
        if call.idempotency:
            execute_body["idempotency_key"] = call.idempotency.key

        if not intent["read_only"]:
            plan_resp = await client.post(
                f"{self.base_url}/api/v1/tools/plan",
                headers=headers,
                json={"query": f"execute {backend}.{operation}", "backend": backend, "read_only": False},
            )
            plan_data = _json_or_text(plan_resp)
            if plan_resp.status_code >= 400:
                return CapabilityResult(
                    ok=False,
                    capability=call.capability,
                    error=f"plan failed HTTP {plan_resp.status_code}",
                    plan_hash=plan_hash,
                    raw=plan_data if isinstance(plan_data, dict) else {"body": plan_data},
                )
            if isinstance(plan_data, dict):
                plan_hash = str(plan_data.get("plan_hash") or plan_hash)
                execute_body["plan_hash"] = plan_hash
                execute_body["intent"] = plan_data.get("intent") or intent
                if plan_data.get("requires_write_confirmation"):
                    execute_body["write_confirmation"] = {
                        "confirmation_token": plan_data.get("confirmation_token"),
                        "confirmation_phrase": plan_data.get("confirmation_phrase"),
                    }

        resp = await client.post(
            f"{self.base_url}/api/v1/tools/execute",
            headers=headers,
            json=execute_body,
        )
        data = _json_or_text(resp)
        ok = resp.status_code < 400
        payload = data if isinstance(data, dict) else {"body": data}
        nested = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        return CapabilityResult(
            ok=ok,
            capability=call.capability,
            data=nested if isinstance(nested, dict) else {"value": nested},
            error=None if ok else f"execute failed HTTP {resp.status_code}",
            plan_hash=plan_hash,
            provider=str((nested or {}).get("provider") or "") if isinstance(nested, dict) else "",
            raw=payload,
        )


class FakeCapabilityClient:
    name = "fake-capability"

    def __init__(self) -> None:
        self.calls: list[CapabilityCall] = []
        self._items: dict[str, dict[str, Any]] = {}
        self._counter = 0

    def status(self) -> dict[str, Any]:
        return {"name": self.name, "wired": True, "mode": "fake"}

    async def call(self, call: CapabilityCall) -> CapabilityResult:
        self.calls.append(call)
        cap = call.capability
        args = dict(call.args)

        if cap == "directory.owner.resolve":
            service = str(args.get("service") or "default")
            return CapabilityResult(
                ok=True,
                capability=cap,
                provider="fake",
                data={
                    "assignee_ref": f"fake:user:{service}",
                    "assignee_name": f"{service}-owner",
                    "channel_ref": "cliq:lab",
                    "owner_source": "fake",
                },
            )
        if cap == "work-item.create":
            self._counter += 1
            ref = f"fake:wi:{self._counter}"
            item = {
                "work_item_ref": ref,
                "title": args.get("title") or "",
                "status": "open",
                "assignee_ref": "",
                "labels": args.get("labels") or {},
            }
            self._items[ref] = item
            return CapabilityResult(ok=True, capability=cap, provider="fake", data=dict(item))
        if cap == "work-item.assign":
            ref = str(args.get("work_item_ref") or "")
            item = self._items.setdefault(ref, {"work_item_ref": ref, "status": "open"})
            item["assignee_ref"] = str(args.get("assignee_ref") or "")
            return CapabilityResult(ok=True, capability=cap, provider="fake", data=dict(item))
        if cap == "work-item.get":
            ref = str(args.get("work_item_ref") or "")
            item = self._items.get(ref) or {
                "work_item_ref": ref,
                "status": "open",
                "assignee_ref": "fake:user:default",
            }
            return CapabilityResult(ok=True, capability=cap, provider="fake", data=dict(item))
        if cap == "work-item.comment":
            return CapabilityResult(
                ok=True,
                capability=cap,
                provider="fake",
                data={"work_item_ref": args.get("work_item_ref"), "ok": True},
            )
        if cap.startswith("observe."):
            kind = cap.split(".", 1)[1].split(".", 1)[0]
            recovery = bool(args.get("recovery"))
            if kind == "metrics":
                if recovery:
                    data = {
                        "kind": kind,
                        "status": "ok",
                        "health": "healthy",
                        "summary": "fake metrics healthy",
                        "points": [[0, 0.0]],
                        "value": 0,
                    }
                else:
                    data = {
                        "kind": kind,
                        "status": "firing",
                        "health": "unhealthy",
                        "summary": "fake metrics unhealthy",
                        "points": [[0, 1.0]],
                        "value": 1,
                    }
            else:
                data = {
                    "kind": kind,
                    "status": "ok" if recovery else "firing",
                    "error_count": 0 if recovery else 1,
                    "summary": f"fake {cap}",
                }
            return CapabilityResult(
                ok=True,
                capability=cap,
                provider="fake",
                data=data,
            )
        if cap == "work-item.transition":
            ref = str(args.get("work_item_ref") or "")
            item = self._items.setdefault(ref, {"work_item_ref": ref})
            item["status"] = str(args.get("status") or "closed")
            return CapabilityResult(ok=True, capability=cap, provider="fake", data=dict(item))
        if cap == "alert.silence.create":
            env = str(args.get("env") or "").strip()
            service = str(args.get("service") or "").strip()
            minutes = int(args.get("minutes") or 60)
            if not env or not service:
                return CapabilityResult(
                    ok=False,
                    capability=cap,
                    error="env and service required",
                    provider="fake",
                )
            if minutes < 5 or minutes > 60 * 24 * 14:
                return CapabilityResult(
                    ok=False,
                    capability=cap,
                    error="duration must be between 5 minutes and 14 days",
                    provider="fake",
                )
            self._counter += 1
            silence_id = f"fake:silence:{self._counter}"
            return CapabilityResult(
                ok=True,
                capability=cap,
                provider="fake",
                data={
                    "silence_id": silence_id,
                    "starts_at": "2026-01-01T00:00:00Z",
                    "ends_at": "2026-01-01T01:00:00Z",
                    "env": env,
                    "service": service,
                    "minutes": minutes,
                },
            )
        if cap in {"alert.silence.get", "alert.silence.expire"}:
            return CapabilityResult(
                ok=True,
                capability=cap,
                provider="fake",
                data={"silence_id": args.get("silence_id") or "", "ok": True},
            )
        if cap.startswith("chat.") or cap.startswith("mail."):
            return CapabilityResult(
                ok=True,
                capability=cap,
                provider="fake",
                data={"sent": True, "args": args},
            )
        if cap == "spt.test-data.prepare":
            return CapabilityResult(
                ok=True,
                capability=cap,
                provider="fake",
                data={"prep_ref": f"fake:prep:{args.get('demand_ref') or 'd'}", "ready": True},
            )
        if cap == "spt.execute":
            return CapabilityResult(
                ok=True,
                capability=cap,
                provider="fake",
                data={
                    "async_operation_ref": f"fake:spt:{args.get('demand_ref') or 'd'}",
                    "status": "accepted",
                },
            )
        if cap == "spt.status":
            return CapabilityResult(
                ok=True,
                capability=cap,
                provider="fake",
                data={
                    "async_operation_ref": args.get("async_operation_ref") or "",
                    "status": "succeeded",
                },
            )
        if cap == "spt.cancel":
            return CapabilityResult(
                ok=True,
                capability=cap,
                provider="fake",
                data={"status": "cancelled"},
            )
        return CapabilityResult(
            ok=True,
            capability=cap,
            data={"echo": args, "fake": True},
            provider="fake",
        )


def _json_or_text(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return resp.text[:1000]
