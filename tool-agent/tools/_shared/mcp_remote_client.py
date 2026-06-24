from __future__ import annotations

import importlib
import json
import sys
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Iterator

_AGENT_ROOT = Path(__file__).resolve().parents[2]


def _blocked_roots() -> set[str]:
    return {_AGENT_ROOT.resolve().as_posix(), Path.cwd().resolve().as_posix()}


def _filtered_sys_path() -> list[str]:
    blocked = _blocked_roots()
    filtered: list[str] = []
    for entry in sys.path:
        path = Path.cwd().resolve().as_posix() if not entry else Path(entry).resolve().as_posix()
        if path not in blocked:
            filtered.append(entry)
    return filtered


@contextmanager
def _pypi_mcp_context() -> Iterator[None]:
    """Import PyPI `mcp` while local `mcp/` package is on sys.path."""
    saved_modules = {
        key: sys.modules.pop(key)
        for key in list(sys.modules)
        if key == "mcp" or key.startswith("mcp.")
    }
    saved_path = sys.path
    sys.path = _filtered_sys_path()
    try:
        yield
    finally:
        sys.path = saved_path
        sys.modules.update(saved_modules)


def parse_tool_result(result: Any) -> Any:
    content = getattr(result, "content", None)
    if not content:
        return result
    first = content[0]
    text = getattr(first, "text", None)
    if text is None:
        return result
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


class RemoteMcpClient:
    """Streamable HTTP MCP client for satellite servers (e.g. kagent-grafana-mcp)."""

    def __init__(self, url: str, *, timeout_seconds: float = 30.0) -> None:
        self.url = url.rstrip("/")
        if not self.url.endswith("/mcp"):
            self.url = f"{self.url}/mcp"
        self.timeout_seconds = timeout_seconds

    @asynccontextmanager
    async def session(self) -> AsyncIterator[Any]:
        with _pypi_mcp_context():
            streamable_http = importlib.import_module("mcp.client.streamable_http")
            mcp_pkg = importlib.import_module("mcp")
            ClientSession = mcp_pkg.ClientSession
            async with streamable_http.streamablehttp_client(self.url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        async with self.session() as session:
            result = await session.call_tool(name, arguments)
            return parse_tool_result(result)

    async def list_tools(self) -> list[str]:
        async with self.session() as session:
            tools = await session.list_tools()
            return [t.name for t in tools.tools]
