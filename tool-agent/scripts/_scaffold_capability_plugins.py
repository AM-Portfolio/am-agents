"""Scaffold generic capability plugins (run once from tool-agent root)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "tools"


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def scaffold_plugin(
    folder: str,
    *,
    name: str,
    display: str,
    provider_env: str,
    default_provider: str,
    allowed: list[str],
    keywords: list[str],
    operations: dict[str, dict],
    memory_impl: str,
    vendor_adapters: dict[str, str],
) -> None:
    base = ROOT / folder
    write(base / "__init__.py", f'"""Generic {name} capability plugin."""\n')
    write(
        base / "manifest.yaml",
        f"""
name: {name}
display_name: {display}
enabled: false
version: "0.1.0"

infer_keywords: {keywords}

env_prefix: {folder.upper()}_

supports_mcp: false
has_entities: false
health_check: skip

prompts:
  intent:
    source: file
    name: tool-agent/intent/{folder}
    label: "{{{{APP_ENV}}}}"
    fallback: prompts/intent.yaml
""",
    )
    ops_yaml = ["adapter: " + name, "operations:"]
    for op, cfg in operations.items():
        ops_yaml.append(f"  {op}:")
        for k, v in cfg.items():
            if isinstance(v, bool):
                ops_yaml.append(f"    {k}: {'true' if v else 'false'}")
            else:
                ops_yaml.append(f"    {k}: {v}")
    write(base / "registry.yaml", "\n".join(ops_yaml))

    write(
        base / "safety.py",
        f'''
from __future__ import annotations

from app.config import settings
from app.models.intent import IntentDocument, SafetyError
from tools._shared.capability.approval import requires_write_confirmation, risk_for_operation

WRITE_OPS = frozenset({{
{chr(10).join(f'    "{op}",' for op, cfg in operations.items() if not cfg.get("read_only", True))}
}})


def validate(intent: IntentDocument, *, request_read_only: bool) -> None:
    risk = risk_for_operation(intent.operation)
    is_write = intent.operation in WRITE_OPS or requires_write_confirmation(risk)
    if request_read_only and is_write:
        raise SafetyError(f"{{intent.backend}}.{{intent.operation}} blocked in read-only mode")
    if is_write and not settings.TOOL_AGENT_ALLOW_WRITES:
        raise SafetyError(f"{{intent.backend}} writes blocked: TOOL_AGENT_ALLOW_WRITES=false")


def validate_tool_params(operation: str, params: dict) -> None:
    _ = params
    if operation not in {{{", ".join(repr(o) for o in operations)}}}:
        raise ValueError(f"unknown operation {{operation!r}}")
''',
    )

    write(
        base / "search" / "__init__.py",
        "from . import parse_rules, resolve\n\n__all__ = ['parse_rules', 'resolve']\n",
    )
    write(
        base / "search" / "parse_rules.py",
        f'''
from __future__ import annotations

from app.models.intent import IntentDocument

_KEYWORDS = {[k.lower() for k in keywords]}


def parse_rules(query: str, *, tool_name: str) -> IntentDocument | None:
    q = (query or "").lower()
    if not any(k in q for k in _KEYWORDS):
        return None
    operation = "get"
    read_only = True
    for candidate in ({", ".join(repr(o) for o in operations)}):
        if candidate.replace(".", " ") in q or candidate in q:
            operation = candidate
            break
    op_read = {{{", ".join(f"{op!r}: {cfg.get('read_only', True)!r}" for op, cfg in operations.items())}}}
    read_only = bool(op_read.get(operation, True))
    return IntentDocument(
        backend=tool_name,
        operation=operation,
        params={{}},
        read_only=read_only,
        confidence=0.7,
        rationale=f"rule match for {{tool_name}}",
    )
''',
    )
    write(
        base / "search" / "resolve.py",
        '''
from __future__ import annotations

from app.models.intent import IntentDocument


def resolve(intent: IntentDocument, query: str) -> tuple[IntentDocument, str | None]:
    _ = query
    return intent, None
''',
    )
    write(
        base / "prompts" / "intent.yaml",
        f"system: |\n  You plan {name} capability operations. Prefer generic ops; never invent vendor names.\n",
    )
    write(base / "common" / "__init__.py", '"""Shared DTOs and helpers for this capability."""\n')
    write(
        base / "common" / "dto.py",
        '''
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CapabilityParams(BaseModel):
    idempotency_key: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
''',
    )
    write(base / "adapters" / "__init__.py", "")
    write(
        base / "adapters" / "memory.py",
        memory_impl,
    )
    for vendor, impl in vendor_adapters.items():
        write(base / "adapters" / vendor / "__init__.py", "")
        write(base / "adapters" / vendor / "adapter.py", impl)

    allowed_repr = ", ".join(repr(a) for a in allowed)
    adapter_imports = []
    adapter_branches = []
    for vendor in vendor_adapters:
        mod = vendor.replace("-", "_")
        adapter_imports.append(
            f"        if provider == {vendor!r}:\n"
            f"            from .adapters.{mod}.adapter import Adapter\n"
            f"            return Adapter()"
        )
    adapter_imports.append(
        "        if provider == 'memory':\n"
        "            from .adapters.memory import MemoryAdapter\n"
        "            return MemoryAdapter()"
    )
    build_body = "\n".join(adapter_imports) + "\n        raise ValueError(f'unknown provider {provider!r}')"

    write(
        base / "plugin.py",
        f'''
from __future__ import annotations

from pathlib import Path
from typing import Any

from tools._shared.capability.plugin_base import CapabilityTool


class {display.replace(" ", "").replace("-", "")}Tool(CapabilityTool):
    provider_env = {provider_env!r}
    default_provider = {default_provider!r}
    allowed_providers = frozenset({{{allowed_repr}}})

    def build_adapter(self, provider: str) -> Any:
{build_body}


def get_tool() -> {display.replace(" ", "").replace("-", "")}Tool:
    return {display.replace(" ", "").replace("-", "")}Tool(Path(__file__).resolve().parent)
''',
    )

    write(
        base / "tests" / "test_plugin_contract.py",
        f'''
from tools._protocol import IntegrationTool
from tools.{folder}.plugin import get_tool


def test_plugin_contract():
    tool = get_tool()
    assert isinstance(tool, IntegrationTool)
    assert tool.name == {name!r}
    assert set(tool.operations()) == {{{", ".join(repr(o) for o in operations)}}}
''',
    )
    write(
        base / "tests" / "test_memory_adapter.py",
        f'''
import pytest

from app.models.intent import IntentDocument
from tools.{folder}.plugin import get_tool


@pytest.mark.asyncio
async def test_memory_execute_roundtrip(monkeypatch):
    monkeypatch.setenv({provider_env!r}, "memory")
    monkeypatch.setenv("TOOL_AGENT_ALLOW_WRITES", "true")
    tool = get_tool()
    ops = tool.operations()
    op = next(iter(ops))
    intent = IntentDocument(
        backend=tool.name,
        operation=op,
        params={{"idempotency_key": "test-1"}},
        read_only=True,
        confidence=1.0,
    )
    # Force read_only false only when needed
    entry = (tool.registry_entry().get("operations") or {{}}).get(op) or {{}}
    if not entry.get("read_only", True):
        intent.read_only = False
    result = await tool.execute(intent, read_only=intent.read_only, max_rows=10)
    assert result["ok"] is True
    assert result["provider"] == "memory"
    assert result["capability"].startswith(tool.name)
''',
    )
    write(
        base / "README.md",
        f"""# {display}

Generic capability plugin. Backend name: `{name}`.

Enable with `TOOL_AGENT_CAPABILITY_PLUGINS={name}` (or set `enabled: true`).

Provider selection: `{provider_env}` (default `{default_provider}`). Allowed: {", ".join(allowed)}.
""",
    )


# ---- work_item ----
scaffold_plugin(
    "work_item",
    name="work-item",
    display="Work Item",
    provider_env="WORK_ITEM_PROVIDER",
    default_provider="memory",
    allowed=["memory", "openproject"],
    keywords=["work-item", "work item", "ticket", "openproject", "workpackage"],
    operations={
        "search": {"adapter_method": "search", "read_only": True, "approval_risk": "read"},
        "get": {"adapter_method": "get", "read_only": True, "approval_risk": "read"},
        "create": {"adapter_method": "create", "read_only": False, "approval_risk": "create"},
        "comment": {"adapter_method": "comment", "read_only": False, "approval_risk": "update"},
        "assign": {"adapter_method": "assign", "read_only": False, "approval_risk": "update"},
        "transition": {"adapter_method": "transition", "read_only": False, "approval_risk": "update"},
    },
    memory_impl='''
from __future__ import annotations

import itertools
import threading
from typing import Any


class MemoryAdapter:
    _counter = itertools.count(1)
    _lock = threading.Lock()
    _items: dict[str, dict[str, Any]] = {}

    @property
    def available(self) -> bool:
        return True

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        _ = read_only
        with self._lock:
            if operation == "create":
                wid = f"mem:wi:{next(self._counter)}"
                item = {
                    "work_item_ref": wid,
                    "title": params.get("title") or "untitled",
                    "description": params.get("description") or "",
                    "status": "open",
                    "assignee_ref": params.get("assignee_ref") or "",
                    "labels": params.get("labels") or {},
                    "comments": [],
                }
                self._items[wid] = item
                return dict(item)
            ref = str(params.get("work_item_ref") or params.get("id") or "")
            if operation == "search":
                q = str(params.get("query") or "").lower()
                hits = [dict(v) for v in self._items.values() if not q or q in str(v).lower()]
                return {"items": hits}
            if not ref or ref not in self._items:
                if operation == "get":
                    raise KeyError(f"work item not found: {ref}")
                raise KeyError(f"work item not found: {ref}")
            item = self._items[ref]
            if operation == "get":
                return dict(item)
            if operation == "comment":
                item["comments"].append(params.get("body") or "")
                return {"work_item_ref": ref, "comments": list(item["comments"])}
            if operation == "assign":
                item["assignee_ref"] = params.get("assignee_ref") or ""
                return {"work_item_ref": ref, "assignee_ref": item["assignee_ref"]}
            if operation == "transition":
                item["status"] = params.get("status") or item["status"]
                return {"work_item_ref": ref, "status": item["status"]}
            raise ValueError(f"unknown operation {operation}")
''',
    vendor_adapters={
        "openproject": '''
from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import quote

from tools.work_item.adapters.openproject.client import OpenProjectClient


def _wp_id(ticket_ref: str) -> int:
    ref = ticket_ref.strip()
    if ref.startswith("op:wp:"):
        return int(ref.split(":", 2)[2])
    if ref.isdigit():
        return int(ref)
    raise ValueError(f"invalid OpenProject work_item_ref: {ticket_ref!r}")


class Adapter:
    def __init__(self) -> None:
        self._client: OpenProjectClient | None = None
        try:
            self._client = OpenProjectClient()
        except Exception:
            self._client = None
        self._project_id = int(os.environ.get("OPENPROJECT_PROJECT_ID", "3"))
        self._type_id = int(os.environ.get("OPENPROJECT_TYPE_ID", "1"))

    @property
    def available(self) -> bool:
        return self._client is not None

    def _public_url(self, wp_id: int) -> str:
        base = os.environ.get("OPENPROJECT_PUBLIC_URL") or os.environ.get("OPENPROJECT_URL", "")
        return f"{base.rstrip('/')}/work_packages/{wp_id}"

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        _ = read_only
        assert self._client is not None
        if operation == "create":
            body = {
                "subject": str(params.get("title") or "Alert")[:255],
                "description": {"format": "plain", "raw": str(params.get("description") or "")[:100_000]},
                "_links": {
                    "project": {"href": f"/api/v3/projects/{self._project_id}"},
                    "type": {"href": f"/api/v3/types/{self._type_id}"},
                },
            }
            data = self._client.post("/api/v3/work_packages", body)
            wp_id = int(data["id"])
            return {
                "work_item_ref": f"op:wp:{wp_id}",
                "url": self._public_url(wp_id),
                "status": "open",
                "lock_version": str(data.get("lockVersion") or ""),
            }
        if operation == "get":
            wp_id = _wp_id(str(params.get("work_item_ref") or params.get("id") or ""))
            data = self._client.get(f"/api/v3/work_packages/{wp_id}")
            assignee = ((data.get("_links") or {}).get("assignee") or {}).get("href") or ""
            return {
                "work_item_ref": f"op:wp:{wp_id}",
                "title": data.get("subject") or "",
                "status": ((data.get("_links") or {}).get("status") or {}).get("title") or "",
                "assignee_ref": assignee,
                "url": self._public_url(wp_id),
                "lock_version": str(data.get("lockVersion") or ""),
                "updated_at": data.get("updatedAt") or "",
            }
        if operation == "search":
            q = str(params.get("query") or "")
            filt = quote(json.dumps([{"subject": {"operator": "**", "values": [q]}}]), safe="")
            data = self._client.get(f"/api/v3/work_packages?filters={filt}&pageSize=20")
            els = (data.get("_embedded") or {}).get("elements") or []
            return {
                "items": [
                    {"work_item_ref": f"op:wp:{el['id']}", "title": el.get("subject") or ""}
                    for el in els
                ]
            }
        if operation == "comment":
            wp_id = _wp_id(str(params.get("work_item_ref") or ""))
            self._client.post(
                f"/api/v3/work_packages/{wp_id}/activities",
                {"comment": {"format": "plain", "raw": str(params.get("body") or "")}},
            )
            return {"work_item_ref": f"op:wp:{wp_id}", "ok": True}
        if operation == "assign":
            wp_id = _wp_id(str(params.get("work_item_ref") or ""))
            data = self._client.get(f"/api/v3/work_packages/{wp_id}")
            lock = int(data["lockVersion"])
            href = str(params.get("assignee_ref") or "")
            if href.isdigit():
                href = f"/api/v3/users/{href}"
            elif href.startswith("op:user:"):
                href = f"/api/v3/users/{href.split(':', 2)[2]}"
            self._client.patch(
                f"/api/v3/work_packages/{wp_id}",
                {"lockVersion": lock, "_links": {"assignee": {"href": href}}},
            )
            return {"work_item_ref": f"op:wp:{wp_id}", "assignee_ref": href}
        if operation == "transition":
            wp_id = _wp_id(str(params.get("work_item_ref") or ""))
            data = self._client.get(f"/api/v3/work_packages/{wp_id}")
            lock = int(data["lockVersion"])
            status_id = params.get("status_id") or params.get("status")
            self._client.patch(
                f"/api/v3/work_packages/{wp_id}",
                {
                    "lockVersion": lock,
                    "_links": {"status": {"href": f"/api/v3/statuses/{status_id}"}},
                },
            )
            return {"work_item_ref": f"op:wp:{wp_id}", "status": str(status_id)}
        raise ValueError(f"unknown operation {operation}")
''',
    },
)

write(
    ROOT / "work_item" / "adapters" / "openproject" / "client.py",
    '''
"""Minimal OpenProject API v3 HTTP client (stdlib only)."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urljoin, urlparse


class OpenProjectClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_token: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("OPENPROJECT_URL", "")).rstrip("/") + "/"
        self.api_token = (api_token or os.environ.get("OPENPROJECT_API_TOKEN", "")).strip()
        self.timeout = timeout
        if not self.base_url.strip("/"):
            raise RuntimeError("OPENPROJECT_URL is required")
        if not self.api_token:
            raise RuntimeError("OPENPROJECT_API_TOKEN is required")

    def _headers(self) -> dict[str, str]:
        raw = f"apikey:{self.api_token}".encode()
        auth = base64.b64encode(raw).decode("ascii")
        headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "am-tool-agent/work-item (OpenProject)",
        }
        parsed = urlparse(self.base_url)
        if parsed.hostname and (
            parsed.hostname.endswith(".svc.cluster.local")
            or parsed.hostname in {"127.0.0.1", "localhost"}
        ):
            public = os.environ.get("OPENPROJECT_PUBLIC_HOST", "openproject.asrax.in").strip()
            headers["Host"] = public
            headers["X-Forwarded-Proto"] = "https"
        return headers

    def request(self, method: str, path: str, *, body: dict[str, Any] | None = None) -> dict[str, Any]:
        url = urljoin(self.base_url, path.lstrip("/"))
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(), method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenProject {method} {path} failed: {exc.code} {detail}") from exc

    def get(self, path: str) -> dict[str, Any]:
        return self.request("GET", path)

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", path, body=body)

    def patch(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return self.request("PATCH", path, body=body)
''',
)

# ---- chat ----
scaffold_plugin(
    "chat",
    name="chat",
    display="Chat",
    provider_env="CHAT_PROVIDER",
    default_provider="memory",
    allowed=["memory", "cliq"],
    keywords=["chat", "cliq", "notify", "message"],
    operations={
        "message.send": {"adapter_method": "message_send", "read_only": False, "approval_risk": "send"},
        "card.send": {"adapter_method": "card_send", "read_only": False, "approval_risk": "send"},
    },
    memory_impl='''
from __future__ import annotations

from typing import Any


class MemoryAdapter:
    sent: list[dict[str, Any]] = []

    @property
    def available(self) -> bool:
        return True

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        _ = read_only
        payload = {"operation": operation, **params}
        self.sent.append(payload)
        return {"message_ref": f"mem:chat:{len(self.sent)}", "channel_ref": params.get("channel_ref") or ""}
''',
    vendor_adapters={
        "cliq": '''
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def _webhook_for_channel(channel_ref: str) -> str:
    ref = (channel_ref or "").strip().lower()
    if ref in {"cliq:lab", "lab"}:
        return os.environ.get("ZOHO_CLIQ_LAB_WEBHOOK_URL", "").strip() or os.environ.get("ZOHO_CLIQ_WEBHOOK_URL", "").strip()
    if ref in {"cliq:prod", "prod"}:
        return os.environ.get("ZOHO_CLIQ_PROD_WEBHOOK_URL", "").strip() or os.environ.get("ZOHO_CLIQ_WEBHOOK_URL", "").strip()
    if ref.startswith("https://"):
        return channel_ref.strip()
    return os.environ.get("ZOHO_CLIQ_WEBHOOK_URL", "").strip()


class Adapter:
    @property
    def available(self) -> bool:
        return bool(os.environ.get("ZOHO_CLIQ_WEBHOOK_URL") or os.environ.get("ZOHO_CLIQ_LAB_WEBHOOK_URL"))

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        _ = read_only
        url = _webhook_for_channel(str(params.get("channel_ref") or ""))
        if not url:
            raise RuntimeError("Cliq webhook URL not configured")
        if operation == "message.send":
            body = {"text": str(params.get("body") or "")[:3500]}
        elif operation == "card.send":
            card = params.get("card") if isinstance(params.get("card"), dict) else {}
            body = {
                "text": str(params.get("body") or card.get("body") or "")[:3500],
                "card": {"title": str(card.get("title") or "Notification")[:100], "theme": "modern-inline"},
            }
        else:
            raise ValueError(f"unknown operation {operation}")
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Cliq send failed: {exc.code}") from exc
        return {"ok": True, "provider_status": raw[:500], "channel_ref": params.get("channel_ref") or ""}
''',
    },
)

# ---- mail ----
scaffold_plugin(
    "mail",
    name="mail",
    display="Mail",
    provider_env="MAIL_PROVIDER",
    default_provider="memory",
    allowed=["memory", "zoho"],
    keywords=["mail", "email", "zoho"],
    operations={
        "message.send": {"adapter_method": "message_send", "read_only": False, "approval_risk": "send"},
    },
    memory_impl='''
from __future__ import annotations

from typing import Any


class MemoryAdapter:
    sent: list[dict[str, Any]] = []

    @property
    def available(self) -> bool:
        return True

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        _ = read_only
        if operation != "message.send":
            raise ValueError(operation)
        self.sent.append(dict(params))
        return {"mail_ref": f"mem:mail:{len(self.sent)}", "to": list(params.get("to") or [])}
''',
    vendor_adapters={
        "zoho": '''
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


class Adapter:
    def __init__(self) -> None:
        self.token = os.environ.get("ZOHO_MAIL_ACCESS_TOKEN", "").strip()
        self.account_id = os.environ.get("ZOHO_MAIL_ACCOUNT_ID", "").strip()
        self.api_base = os.environ.get("ZOHO_MAIL_API_BASE", "https://mail.zoho.com/api").rstrip("/")
        self.from_addr = os.environ.get("ZOHO_MAIL_FROM", "").strip()

    @property
    def available(self) -> bool:
        return bool(self.token and self.account_id and self.from_addr)

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        _ = read_only
        if operation != "message.send":
            raise ValueError(operation)
        if not self.available:
            raise RuntimeError("Zoho mail credentials not configured")
        payload = {
            "fromAddress": self.from_addr,
            "toAddress": ",".join(params.get("to") or []),
            "ccAddress": ",".join(params.get("cc") or []),
            "subject": params.get("subject") or "",
            "content": params.get("html_body") or params.get("text_body") or "",
            "mailFormat": "html" if params.get("html_body") else "plaintext",
        }
        url = f"{self.api_base}/accounts/{self.account_id}/messages"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Zoho-oauthtoken {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Zoho mail send failed: {exc.code}") from exc
        return {"ok": True, "provider_status": raw[:500]}
''',
    },
)

# ---- document ----
scaffold_plugin(
    "document",
    name="document",
    display="Document",
    provider_env="DOCUMENT_PROVIDER",
    default_provider="memory",
    allowed=["memory", "minio"],
    keywords=["document", "docstore", "minio", "object"],
    operations={
        "put": {"adapter_method": "put", "read_only": False, "approval_risk": "create"},
        "get": {"adapter_method": "get", "read_only": True, "approval_risk": "read"},
        "exists": {"adapter_method": "exists", "read_only": True, "approval_risk": "read"},
        "signed-url.create": {"adapter_method": "signed_url_create", "read_only": True, "approval_risk": "read"},
    },
    memory_impl='''
from __future__ import annotations

import base64
import hashlib
from typing import Any


class MemoryAdapter:
    _objects: dict[str, dict[str, Any]] = {}

    @property
    def available(self) -> bool:
        return True

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        _ = read_only
        key = str(params.get("object_key") or params.get("key") or "").lstrip("/")
        bucket = str(params.get("bucket") or "memory")
        ref = f"memory:{bucket}/{key}"
        if operation == "put":
            content = params.get("content")
            if isinstance(content, str):
                raw = base64.b64decode(content) if params.get("content_encoding") == "base64" else content.encode()
            else:
                raw = bytes(content or b"")
            checksum = hashlib.sha256(raw).hexdigest()
            self._objects[ref] = {
                "content": raw,
                "content_type": params.get("content_type") or "application/octet-stream",
                "checksum": checksum,
            }
            return {"object_key": key, "bucket": bucket, "checksum": checksum, "docs_ref": ref, "size_bytes": len(raw)}
        if operation == "get":
            obj = self._objects.get(ref) or self._objects.get(str(params.get("docs_ref") or ""))
            if not obj:
                raise KeyError(f"document not found: {ref}")
            return {
                "docs_ref": ref,
                "content_base64": base64.b64encode(obj["content"]).decode("ascii"),
                "content_type": obj["content_type"],
                "checksum": obj["checksum"],
            }
        if operation == "exists":
            exists = ref in self._objects or str(params.get("docs_ref") or "") in self._objects
            return {"exists": exists, "docs_ref": ref}
        if operation == "signed-url.create":
            return {"url": f"memory://{bucket}/{key}", "docs_ref": ref, "expires_in": 3600}
        raise ValueError(operation)
''',
    vendor_adapters={
        "minio": '''
from __future__ import annotations

import base64
import io
import os
from typing import Any
from urllib.parse import urlparse


class Adapter:
    def __init__(self) -> None:
        self._client = None
        self._bucket = (os.environ.get("MINIO_BUCKET") or "agent-docs").strip()
        endpoint = (os.environ.get("MINIO_ENDPOINT") or "").strip()
        access_key = (os.environ.get("MINIO_ACCESS_KEY") or "").strip()
        secret_key = (os.environ.get("MINIO_SECRET_KEY") or "").strip()
        if not (endpoint and access_key and secret_key):
            return
        try:
            from minio import Minio
        except ImportError:
            return
        parsed = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
        host = parsed.hostname or endpoint
        port = parsed.port
        secure = parsed.scheme == "https"
        endpoint_host = f"{host}:{port}" if port else host
        self._client = Minio(endpoint_host, access_key=access_key, secret_key=secret_key, secure=secure)

    @property
    def available(self) -> bool:
        return self._client is not None

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        _ = read_only
        assert self._client is not None
        bucket = str(params.get("bucket") or self._bucket)
        key = str(params.get("object_key") or params.get("key") or "").lstrip("/")
        if operation == "put":
            content = params.get("content")
            if isinstance(content, str):
                raw = base64.b64decode(content) if params.get("content_encoding") == "base64" else content.encode()
            else:
                raw = bytes(content or b"")
            if not self._client.bucket_exists(bucket):
                self._client.make_bucket(bucket)
            self._client.put_object(
                bucket,
                key,
                io.BytesIO(raw),
                length=len(raw),
                content_type=str(params.get("content_type") or "application/octet-stream"),
            )
            return {"docs_ref": f"minio:{bucket}/{key}", "bucket": bucket, "object_key": key, "size_bytes": len(raw)}
        if operation == "get":
            resp = self._client.get_object(bucket, key)
            try:
                raw = resp.read()
            finally:
                resp.close()
                resp.release_conn()
            return {
                "docs_ref": f"minio:{bucket}/{key}",
                "content_base64": base64.b64encode(raw).decode("ascii"),
            }
        if operation == "exists":
            try:
                self._client.stat_object(bucket, key)
                exists = True
            except Exception:
                exists = False
            return {"exists": exists, "docs_ref": f"minio:{bucket}/{key}"}
        if operation == "signed-url.create":
            from datetime import timedelta

            url = self._client.presigned_get_object(bucket, key, expires=timedelta(hours=1))
            return {"url": url, "docs_ref": f"minio:{bucket}/{key}", "expires_in": 3600}
        raise ValueError(operation)
''',
    },
)

# ---- directory ----
scaffold_plugin(
    "directory",
    name="directory",
    display="Directory",
    provider_env="DIRECTORY_PROVIDER",
    default_provider="memory",
    allowed=["memory", "openproject"],
    keywords=["directory", "owner", "assignee", "oncall"],
    operations={
        "owner.resolve": {"adapter_method": "owner_resolve", "read_only": True, "approval_risk": "read"},
    },
    memory_impl='''
from __future__ import annotations

from typing import Any


class MemoryAdapter:
    @property
    def available(self) -> bool:
        return True

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        _ = read_only
        if operation != "owner.resolve":
            raise ValueError(operation)
        service = str(params.get("service") or params.get("team") or "default")
        return {
            "assignee_ref": f"mem:user:{service}",
            "assignee_name": f"{service}-owner",
            "assignee_email": f"{service}@example.com",
            "channel_ref": "cliq:lab",
            "owner_source": "memory",
        }
''',
    vendor_adapters={
        "openproject": '''
from __future__ import annotations

import os
from typing import Any

from tools.work_item.adapters.openproject.client import OpenProjectClient


class Adapter:
    def __init__(self) -> None:
        self._client: OpenProjectClient | None = None
        try:
            self._client = OpenProjectClient()
        except Exception:
            self._client = None
        self._project_id = int(os.environ.get("OPENPROJECT_PROJECT_ID", "3"))

    @property
    def available(self) -> bool:
        return self._client is not None

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        _ = read_only
        if operation != "owner.resolve":
            raise ValueError(operation)
        assert self._client is not None
        # Best-effort: first project membership as owner; callers should refine with catalog.
        data = self._client.get(f"/api/v3/projects/{self._project_id}/available_assignees?pageSize=1")
        els = (data.get("_embedded") or {}).get("elements") or []
        if not els:
            raise RuntimeError("no OpenProject assignees available")
        user = els[0]
        return {
            "assignee_ref": f"op:user:{user.get('id')}",
            "assignee_name": user.get("name") or "",
            "assignee_email": user.get("email") or "",
            "channel_ref": params.get("channel_ref") or "cliq:lab",
            "owner_source": "openproject",
        }
''',
    },
)

# ---- observe ----
scaffold_plugin(
    "observe",
    name="observe",
    display="Observe",
    provider_env="OBSERVE_PROVIDER",
    default_provider="memory",
    allowed=["memory", "grafana"],
    keywords=["observe", "metrics", "logs", "timeseries", "grafana"],
    operations={
        "metrics.query": {"adapter_method": "metrics_query", "read_only": True, "approval_risk": "read"},
        "logs.query": {"adapter_method": "logs_query", "read_only": True, "approval_risk": "read"},
        "timeseries.query": {"adapter_method": "timeseries_query", "read_only": True, "approval_risk": "read"},
    },
    memory_impl='''
from __future__ import annotations

from typing import Any


class MemoryAdapter:
    @property
    def available(self) -> bool:
        return True

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        _ = read_only
        kind = operation.split(".", 1)[0]
        return {
            "kind": kind,
            "query_ref": params.get("query_ref") or params.get("query") or "",
            "status": "ok",
            "summary": f"memory {operation}",
            "points": [],
        }
''',
    vendor_adapters={
        "grafana": '''
from __future__ import annotations

from typing import Any


class Adapter:
    """Delegates to the existing grafana plugin adapter when available."""

    def __init__(self) -> None:
        self._grafana = None
        try:
            from tools.grafana.adapter import GrafanaAdapter

            self._grafana = GrafanaAdapter()
        except Exception:
            self._grafana = None

    @property
    def available(self) -> bool:
        return bool(self._grafana and getattr(self._grafana, "available", False))

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        assert self._grafana is not None
        mapping = {
            "metrics.query": "query_metrics",
            "logs.query": "query_logs",
            "timeseries.query": "query_metrics",
        }
        grafana_op = mapping.get(operation)
        if not grafana_op:
            raise ValueError(operation)
        data = await self._grafana.execute(grafana_op, params, read_only=read_only, max_rows=100)
        return {
            "kind": operation.split(".", 1)[0],
            "query_ref": params.get("query_ref") or params.get("query") or "",
            "status": "ok",
            "summary": f"grafana:{grafana_op}",
            "data": data if isinstance(data, dict) else {"value": data},
        }
''',
    },
)

# ---- spt ----
scaffold_plugin(
    "spt",
    name="spt",
    display="SPT",
    provider_env="SPT_PROVIDER",
    default_provider="memory",
    allowed=["memory", "k6"],
    keywords=["spt", "synthetic", "performance", "load test", "k6"],
    operations={
        "test-data.prepare": {"adapter_method": "test_data_prepare", "read_only": False, "approval_risk": "create"},
        "execute": {"adapter_method": "execute", "read_only": False, "approval_risk": "execute"},
        "status": {"adapter_method": "status", "read_only": True, "approval_risk": "read"},
        "cancel": {"adapter_method": "cancel", "read_only": False, "approval_risk": "update"},
    },
    memory_impl='''
from __future__ import annotations

import itertools
import threading
from typing import Any


class MemoryAdapter:
    _counter = itertools.count(1)
    _lock = threading.Lock()
    _runs: dict[str, dict[str, Any]] = {}

    @property
    def available(self) -> bool:
        return True

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        _ = read_only
        with self._lock:
            if operation == "test-data.prepare":
                prep_ref = f"mem:prep:{next(self._counter)}"
                return {"prep_ref": prep_ref, "demand_ref": params.get("demand_ref") or "", "ready": True}
            if operation == "execute":
                run_ref = f"mem:spt:{next(self._counter)}"
                self._runs[run_ref] = {"status": "running", "demand_ref": params.get("demand_ref") or ""}
                return {"async_operation_ref": run_ref, "status": "running"}
            ref = str(params.get("async_operation_ref") or params.get("run_ref") or "")
            if operation == "status":
                run = self._runs.get(ref) or {"status": "unknown"}
                return {"async_operation_ref": ref, **run}
            if operation == "cancel":
                if ref in self._runs:
                    self._runs[ref]["status"] = "cancelled"
                return {"async_operation_ref": ref, "status": "cancelled"}
            raise ValueError(operation)
''',
    vendor_adapters={
        "k6": '''
from __future__ import annotations

import os
from typing import Any


class Adapter:
    """Sandbox-gated k6 engine stub — real process execution lands with SPT parity."""

    @property
    def available(self) -> bool:
        return os.environ.get("SPT_K6_ENABLED", "false").lower() in {"1", "true", "yes"}

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        _ = read_only
        if not params.get("sandbox", True) and os.environ.get("SPT_ALLOW_UNSANDBOXED", "false").lower() not in {
            "1",
            "true",
            "yes",
        }:
            raise RuntimeError("k6 SPT requires sandbox=true")
        if operation == "test-data.prepare":
            return {"prep_ref": f"k6:prep:{params.get('demand_ref') or 'default'}", "ready": True}
        if operation == "execute":
            return {
                "async_operation_ref": f"k6:run:{params.get('demand_ref') or 'default'}",
                "status": "accepted",
                "engine": "k6",
            }
        if operation == "status":
            return {"async_operation_ref": params.get("async_operation_ref") or "", "status": "succeeded", "engine": "k6"}
        if operation == "cancel":
            return {"async_operation_ref": params.get("async_operation_ref") or "", "status": "cancelled", "engine": "k6"}
        raise ValueError(operation)
''',
    },
)

print("all capability plugins scaffolded")
