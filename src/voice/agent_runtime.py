from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any
from uuid import UUID

from agent.events import (
    AckEvent,
    DoneEvent as RuntimeDoneEvent,
    ErrorEvent,
    Event,
    ThinkingDelta,
    TextDelta,
    ToolEnd,
    ToolStart,
)

from .agent_base import AgentBackend, AgentEvent, TokenEvent, TurnEndEvent

if TYPE_CHECKING:
    from agent.mcp.registry import MCPRegistry
    from agent.providers.base import LLMClient
    from agent.runtime import AgentRuntime

log = logging.getLogger(__name__)

_VOICE_ERROR_MESSAGES = {
    "provider": "The model provider is having trouble right now. Please try again in a moment.",
    "provider_stream": "The model provider is having trouble right now. Please try again in a moment.",
    "internal": "I hit an internal error. Please try again.",
}


class RuntimeAgent(AgentBackend):
    """Adapter from the lightweight `src/agent` runtime to the voice backend API.

    `src/agent` is turn-based: each call to `run_turn()` consumes one user
    message and finishes with an `agent.events.DoneEvent`. The voice session is
    conversation-based, so that runtime "done" maps to `TurnEndEvent`, keeping
    the microphone open for the next spoken turn.
    """

    def __init__(
        self,
        config_path: str | None = None,
        *,
        config: Any | None = None,
        greeting: str | None = "Hi, I'm ready.",
        user_id: str | None = None,
        database_url: str | None = None,
        pool_min_size: int = 1,
        pool_max_size: int = 10,
    ) -> None:
        self._config_path = config_path
        self._config = config
        self._greeting = greeting
        self._user_id = user_id
        self._database_url = database_url
        self._pool_min_size = pool_min_size
        self._pool_max_size = pool_max_size

        self._runtime: AgentRuntime | None = None
        self._mcp: MCPRegistry | None = None
        self._llm: LLMClient | None = None
        self._pool: Any | None = None
        self._conversation_id: UUID | None = None

    async def start(self, params: dict[str, Any]) -> AsyncIterator[AgentEvent]:
        await self._ensure_runtime()
        self._user_id = _str_or_none(params.get("user_id")) or self._user_id
        self._conversation_id = _uuid_or_none(params.get("conversation_id"))

        initial_text = _first_string(params, "initial_user_text", "user_text", "text", "message")
        if initial_text:
            async for ev in self._run_turn(initial_text):
                yield ev
            return

        greeting = params.get("greeting", self._greeting)
        if isinstance(greeting, str) and greeting.strip():
            yield TokenEvent(text=greeting.strip())
        yield TurnEndEvent(info={"conversation_id": str(self._conversation_id) if self._conversation_id else None})

    async def resume(self, user_text: str) -> AsyncIterator[AgentEvent]:
        await self._ensure_runtime()
        async for ev in self._run_turn(user_text):
            yield ev

    async def close(self) -> None:
        if self._mcp is not None:
            await self._mcp.aclose()
            self._mcp = None
        if self._llm is not None:
            await self._llm.aclose()
            self._llm = None
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
        self._runtime = None

    async def _ensure_runtime(self) -> None:
        if self._runtime is not None:
            return
        from agent.config import AgentConfig, load_agent_config
        from agent.db.pool import create_pool
        from agent.mcp.registry import MCPRegistry
        from agent.providers.factory import make_provider
        from agent.runtime import AgentRuntime
        from agent.tools.base import ToolRegistry

        if isinstance(self._config, AgentConfig):
            cfg = self._config
        elif isinstance(self._config, dict):
            cfg = AgentConfig.model_validate(self._config)
        else:
            cfg = load_agent_config(self._config_path)
        self._pool = await create_pool(
            self._database_url,
            min_size=self._pool_min_size,
            max_size=self._pool_max_size,
        )
        tools = ToolRegistry()
        self._mcp = MCPRegistry(tools)
        await self._mcp.start(cfg.mcp_servers)
        self._llm = make_provider(cfg.provider)
        self._runtime = AgentRuntime(cfg=cfg, pool=self._pool, llm=self._llm, tools=tools)
        log.info("runtime agent ready: agent_id=%s provider=%s model=%s", cfg.agent_id, cfg.provider, cfg.model)

    async def _run_turn(self, user_text: str) -> AsyncIterator[AgentEvent]:
        assert self._runtime is not None
        saw_done = False
        async for ev in self._runtime.run_turn(
            user_text=user_text,
            conversation_id=self._conversation_id,
            user_id=self._user_id,
        ):
            async for out in self._map_event(ev):
                yield out
            if isinstance(ev, RuntimeDoneEvent):
                saw_done = True
        if not saw_done:
            yield TurnEndEvent(info={"conversation_id": str(self._conversation_id) if self._conversation_id else None})

    async def _map_event(self, ev: Event) -> AsyncIterator[AgentEvent]:
        if isinstance(ev, AckEvent):
            yield TokenEvent(text=ev.text)
        elif isinstance(ev, TextDelta):
            yield TokenEvent(text=ev.text)
        elif isinstance(ev, ThinkingDelta):
            return
        elif isinstance(ev, RuntimeDoneEvent):
            self._conversation_id = ev.conversation_id
            yield TurnEndEvent(
                info={
                    "conversation_id": str(ev.conversation_id),
                    "message_id": str(ev.message_id) if ev.message_id else None,
                    "total_ms": ev.total_ms,
                }
            )
        elif isinstance(ev, ErrorEvent):
            yield TokenEvent(text=_spoken_error_message(ev))
        elif isinstance(ev, ToolStart):
            log.info("runtime tool start: %s args=%s", ev.tool_name, ev.args)
        elif isinstance(ev, ToolEnd):
            status = "ok" if ev.ok else f"error={ev.error}"
            log.info("runtime tool end: %s %sms %s", ev.tool_name, ev.latency_ms, status)


def _first_string(params: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _str_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _uuid_or_none(value: Any) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str) and value.strip():
        return UUID(value)
    return None


def _spoken_error_message(ev: ErrorEvent) -> str:
    return _VOICE_ERROR_MESSAGES.get(ev.kind, "I hit an error. Please try again.")
