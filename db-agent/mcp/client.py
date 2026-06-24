from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _expand_env(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        return os.environ.get(match.group(1), "")

    return _ENV_PATTERN.sub(repl, value)


class MCPClient:
    """Minimal MCP client over stdio (JSON-RPC) or HTTP streamable."""

    def __init__(
        self,
        *,
        transport: str,
        command: str | None = None,
        args: list[str] | None = None,
        url: str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self.transport = transport
        self.command = command
        self.args = [_expand_env(a) for a in (args or [])]
        self.url = url
        self.env = env or {}
        self._proc: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._initialized = False

    async def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _start_stdio(self) -> None:
        if self._proc and self._proc.returncode is None:
            return
        if not self.command:
            raise RuntimeError("stdio MCP requires command")
        self._proc = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, **self.env},
        )

    async def _rpc_stdio(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if self.transport != "stdio":
            raise RuntimeError("_rpc_stdio only for stdio transport")
        if not self._initialized:
            await self._start_stdio()
            assert self._proc and self._proc.stdin and self._proc.stdout
            req_id = await self._next_id()
            init_payload = {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "db-agent", "version": "0.1.0"},
                },
            }
            self._proc.stdin.write((json.dumps(init_payload) + "\n").encode())
            await self._proc.stdin.drain()
            await self._read_response(req_id)
            notify = {"jsonrpc": "2.0", "method": "notifications/initialized"}
            self._proc.stdin.write((json.dumps(notify) + "\n").encode())
            await self._proc.stdin.drain()
            self._initialized = True

        assert self._proc and self._proc.stdin and self._proc.stdout
        req_id = await self._next_id()
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            payload["params"] = params
        self._proc.stdin.write((json.dumps(payload) + "\n").encode())
        await self._proc.stdin.drain()
        return await self._read_response(req_id)

    async def _read_response(self, req_id: int) -> Any:
        assert self._proc and self._proc.stdout
        while True:
            raw = await asyncio.wait_for(
                self._proc.stdout.readline(),
                timeout=settings.DB_AGENT_TIMEOUT_SECONDS,
            )
            if not raw:
                raise RuntimeError("MCP server closed stdout")
            msg = json.loads(raw.decode())
            if msg.get("id") == req_id:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result")

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if self.transport == "http":
            return await self._call_tool_http(name, arguments)
        result = await self._rpc_stdio(
            "tools/call",
            {"name": name, "arguments": arguments},
        )
        content = result.get("content") if isinstance(result, dict) else result
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict) and "text" in first:
                try:
                    return json.loads(first["text"])
                except json.JSONDecodeError:
                    return first["text"]
        return content

    async def _call_tool_http(self, name: str, arguments: dict[str, Any]) -> Any:
        if not self.url:
            raise RuntimeError("HTTP MCP requires url")
        endpoint = self.url.rstrip("/") + "/mcp"
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        async with httpx.AsyncClient(timeout=settings.DB_AGENT_TIMEOUT_SECONDS) as client:
            resp = await client.post(endpoint, json=payload)
            resp.raise_for_status()
            data = resp.json()
        if "error" in data:
            raise RuntimeError(data["error"])
        return data.get("result")

    async def close(self) -> None:
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._proc.kill()
