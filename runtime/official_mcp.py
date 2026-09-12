"""Optional adapter for the official MCP Python SDK.

The core MVP uses ``LocalMCPClient`` so tests stay deterministic and offline.
This adapter keeps the same synchronous ``list_tools`` / ``call_tool`` shape
while owning one persistent stdio MCP session in a background event loop.
Install the optional dependency with ``pip install 'mcp>=2.0,<3.0'``.
"""

from __future__ import annotations

import asyncio
import json
import threading
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any

from .tools import ToolSpec


@dataclass(frozen=True)
class MCPServerConfig:
    command: str
    args: tuple[str, ...] = ()
    env: dict[str, str] | None = None


class OfficialMCPClient:
    """Synchronous facade over one official MCP stdio client session.

    The runtime calls tools synchronously. MCP itself is asynchronous, so a
    dedicated thread owns the event loop and session. This avoids calling
    ``asyncio.run`` for every tool invocation and makes session lifetime and
    cleanup explicit.
    """

    def __init__(self, config: MCPServerConfig, *, startup_timeout: float = 10.0) -> None:
        self.config = config
        self.startup_timeout = startup_timeout
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._session: Any = None
        self._ready = threading.Event()
        self._closed = threading.Event()
        self._startup_error: BaseException | None = None

    def __enter__(self) -> "OfficialMCPClient":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._ready.clear()
        self._closed.clear()
        self._startup_error = None
        self._thread = threading.Thread(target=self._run_loop, name="mcp-client", daemon=True)
        self._thread.start()
        if not self._ready.wait(self.startup_timeout):
            self.close()
            raise TimeoutError(f"MCP server did not initialize within {self.startup_timeout:.1f}s")
        if self._startup_error is not None:
            error = self._startup_error
            self.close()
            raise RuntimeError(f"MCP client startup failed: {error}") from error

    def close(self) -> None:
        loop = self._loop
        if loop and loop.is_running():
            loop.call_soon_threadsafe(self._closed.set)
            if self._thread and threading.current_thread() is not self._thread:
                self._thread.join(timeout=self.startup_timeout)
        self._loop = None
        self._session = None
        self._thread = None

    def list_tools(self) -> list[ToolSpec]:
        result = self._submit(self._list_tools())
        return [
            ToolSpec(
                name=str(tool.name),
                description=str(getattr(tool, "description", "") or ""),
                input_schema={str(key): "any" for key in (getattr(tool, "inputSchema", {}) or {}).get("properties", {})},
            )
            for tool in getattr(result, "tools", [])
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        result = self._submit(self._call_tool(name, arguments))
        if getattr(result, "isError", False):
            raise RuntimeError(f"MCP tool returned an error: {name}")
        structured = getattr(result, "structuredContent", None)
        if structured is not None:
            return structured
        content = getattr(result, "content", []) or []
        values: list[Any] = []
        for item in content:
            if hasattr(item, "text"):
                values.append(item.text)
            elif hasattr(item, "data"):
                values.append(item.data)
            else:
                values.append(item.model_dump() if hasattr(item, "model_dump") else item)
        if len(values) == 1 and isinstance(values[0], str):
            try:
                return json.loads(values[0])
            except json.JSONDecodeError:
                pass
        return values[0] if len(values) == 1 else values

    async def _list_tools(self) -> Any:
        return await self._session.list_tools()

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return await self._session.call_tool(name, arguments=arguments)

    def _submit(self, coroutine: Any) -> Any:
        self.start()
        if self._loop is None:
            raise RuntimeError("MCP event loop is not available")
        future: Future[Any] = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        try:
            return future.result(timeout=self.startup_timeout)
        except Exception:
            future.cancel()
            raise

    def _run_loop(self) -> None:
        try:
            asyncio.run(self._session_main())
        except BaseException as exc:  # propagate startup failures to caller
            self._startup_error = exc
            self._ready.set()

    async def _session_main(self) -> None:
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as exc:
            raise RuntimeError("Official MCP adapter requires optional dependency: pip install 'mcp>=2.0,<3.0'") from exc

        self._loop = asyncio.get_running_loop()
        server = StdioServerParameters(command=self.config.command, args=list(self.config.args), env=self.config.env)
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                self._session = session
                await session.initialize()
                self._ready.set()
                await asyncio.to_thread(self._closed.wait)
        self._session = None
