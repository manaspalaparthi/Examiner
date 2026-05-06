from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from typing import Any

from ..config import MCPServerConfig
from ..errors import MCPError
from ..tools.base import ToolContext, ToolRegistry, ToolResult, ToolSpec

log = logging.getLogger(__name__)


class MCPRegistry:
    """Manages MCP server connections and exposes their tools as ToolSpecs.

    Lifecycle:
      - `start(servers)` connects to each enabled server, lists its tools,
        and registers them into the provided ToolRegistry under
        ``<server>__<tool>`` names.
      - `aclose()` tears down all sessions cleanly.

    A failure on one server is logged and that server's tools are skipped;
    the remaining servers come up normally.
    """

    NAMESPACE_SEP = "__"

    def __init__(self, registry: ToolRegistry, *, default_groups: tuple[str, ...] = ("mcp",)) -> None:
        self._registry = registry
        self._stack = AsyncExitStack()
        self._sessions: dict[str, Any] = {}  # name -> ClientSession
        self._default_groups = default_groups

    async def start(self, servers: list[MCPServerConfig]) -> None:
        for cfg in servers:
            if not cfg.enabled:
                continue
            try:
                await asyncio.wait_for(self._connect(cfg), timeout=cfg.timeout_s)
            except Exception as e:
                log.warning("mcp: failed to start server %s: %s", cfg.name, e)

    async def _connect(self, cfg: MCPServerConfig) -> None:
        try:
            from mcp import ClientSession
        except ImportError as e:
            raise MCPError("mcp package not installed") from e

        if cfg.transport == "stdio":
            from mcp import StdioServerParameters
            from mcp.client.stdio import stdio_client
            if not cfg.command:
                raise MCPError(f"mcp server {cfg.name}: stdio transport needs `command`")
            params = StdioServerParameters(command=cfg.command[0], args=list(cfg.command[1:]))
            transport = await self._stack.enter_async_context(stdio_client(params))
        elif cfg.transport == "sse":
            from mcp.client.sse import sse_client
            if not cfg.url:
                raise MCPError(f"mcp server {cfg.name}: sse transport needs `url`")
            transport = await self._stack.enter_async_context(sse_client(cfg.url))
        else:
            raise MCPError(f"unknown mcp transport: {cfg.transport}")

        read, write = transport
        session = await self._stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        listed = await session.list_tools()
        self._sessions[cfg.name] = session

        groups = self._default_groups + (f"mcp:{cfg.name}",)
        for t in listed.tools:
            ns_name = f"{cfg.name}{self.NAMESPACE_SEP}{t.name}"
            params = t.inputSchema or {"type": "object", "properties": {}}
            self._registry.register(ToolSpec(
                name=ns_name,
                description=t.description or f"MCP tool {t.name} on {cfg.name}",
                handler=_make_handler(self, cfg.name, t.name, cfg.timeout_s),
                parameters=params,
                groups=groups,
                server=cfg.name,
            ))
            log.info("mcp: registered %s (server=%s)", ns_name, cfg.name)

    async def call(self, server: str, tool: str, args: dict[str, Any], timeout_s: float) -> ToolResult:
        session = self._sessions.get(server)
        if session is None:
            raise MCPError(f"mcp server not connected: {server}")
        try:
            res = await asyncio.wait_for(
                session.call_tool(tool, arguments=args),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError as e:
            raise MCPError(f"mcp call timed out: {server}/{tool}") from e
        except Exception as e:
            raise MCPError(f"mcp call failed: {server}/{tool}: {e}") from e

        text_parts: list[str] = []
        for block in getattr(res, "content", []) or []:
            t = getattr(block, "text", None)
            if isinstance(t, str):
                text_parts.append(t)
        output = "\n".join(text_parts) if text_parts else ""
        is_error = bool(getattr(res, "isError", False))
        if is_error:
            raise MCPError(f"mcp tool returned error: {output[:400]}")
        return ToolResult(output=output, metadata={"server": server, "tool": tool})

    async def aclose(self) -> None:
        await self._stack.aclose()
        self._sessions.clear()


def _make_handler(reg: MCPRegistry, server: str, tool: str, timeout_s: float):
    async def handler(args: Any, ctx: ToolContext) -> ToolResult:
        if hasattr(args, "model_dump"):
            args = args.model_dump()
        return await reg.call(server, tool, dict(args or {}), timeout_s)
    return handler
