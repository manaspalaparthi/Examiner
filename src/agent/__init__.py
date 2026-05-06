"""Lightweight agent runtime: streaming, tools, MCP, persistent threads.

Public entry points:
    from agent.runtime import AgentRuntime
    from agent.events import AckEvent, TextDelta, ThinkingDelta, ToolStart, ToolEnd, DoneEvent, ErrorEvent

Submodules are imported explicitly so heavy dependencies (asyncpg, httpx,
provider SDKs) are only loaded by callers that actually use them.
"""
