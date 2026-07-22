from __future__ import annotations

import importlib
import json
import sys
from contextlib import asynccontextmanager, contextmanager
from typing import Any, AsyncIterator, Iterator


@contextmanager
def _pypi_mcp_context() -> Iterator[None]:
    saved_modules = {
        key: sys.modules.pop(key)
        for key in list(sys.modules)
        if key == "mcp" or key.startswith("mcp.")
    }
    saved_path = list(sys.path)
    cwd = __import__("pathlib").Path.cwd().resolve().as_posix()
    sys.path = [p for p in sys.path if p and __import__("pathlib").Path(p).resolve().as_posix() != cwd]
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
    """Streamable HTTP MCP client (pattern from tool-agent)."""

    def __init__(
        self,
        url: str,
        *,
        timeout_seconds: float = 60.0,
        bearer_token: str | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        if not self.url.endswith("/mcp"):
            self.url = f"{self.url}/mcp"
        self.timeout_seconds = timeout_seconds
        self.bearer_token = bearer_token

    @asynccontextmanager
    async def session(self) -> AsyncIterator[Any]:
        with _pypi_mcp_context():
            streamable_http = importlib.import_module("mcp.client.streamable_http")
            mcp_pkg = importlib.import_module("mcp")
            ClientSession = mcp_pkg.ClientSession
            headers = {}
            if self.bearer_token:
                headers["Authorization"] = f"Bearer {self.bearer_token}"
            async with streamable_http.streamablehttp_client(
                self.url,
                headers=headers or None,
            ) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        async with self.session() as session:
            result = await session.call_tool(name, arguments)
            return parse_tool_result(result)

    async def list_tools(self) -> list[dict[str, Any]]:
        async with self.session() as session:
            tools = await session.list_tools()
            return [{"name": t.name, "description": getattr(t, "description", "")} for t in tools.tools]
