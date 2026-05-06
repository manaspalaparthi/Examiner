from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    import asyncpg

from .ack import AckPicker
from .config import AgentConfig
from .context import build_messages, build_system_prompt
from .db.repo import ConversationRepo, MessageRepo, TraceRepo
from .errors import ProviderError, ToolError, ToolValidationError
from .events import (
    AckEvent,
    DoneEvent,
    ErrorEvent,
    Event,
    ThinkingDelta,
    TextDelta,
    ToolEnd,
    ToolStart,
)
from .providers.base import (
    LLMClient,
    LLMError,
    LLMFinish,
    LLMThinkingDelta,
    LLMTextDelta,
    LLMToolCall,
    ProviderMessage,
    ProviderToolCall,
)
from .subagents import SubagentSettings, make_delegation_tool
from .tools.base import ToolContext, ToolRegistry, ToolResult, ToolSpec, validate_args
from .tracing import TraceLogger

log = logging.getLogger(__name__)

_CONTENT_INLINE_CAP = 32 * 1024  # bytes
_PROVIDER_ERROR_MESSAGE = (
    "The model provider is having trouble right now. Please try again in a moment."
)
_INTERNAL_ERROR_MESSAGE = "I hit an internal error. Please try again."


class AgentRuntime:
    """Orchestrates one user turn: ack → LLM/tool loop → final assistant message."""

    def __init__(
        self,
        *,
        cfg: AgentConfig,
        pool: asyncpg.Pool,
        llm: LLMClient,
        tools: ToolRegistry,
    ) -> None:
        self._cfg = cfg
        self._pool = pool
        self._llm = llm
        self._tools = tools
        self._convs = ConversationRepo(pool)
        self._msgs = MessageRepo(pool)
        self._traces = TraceRepo(pool)
        self._ack = AckPicker(cfg.ack.phrases) if cfg.ack.enabled and cfg.ack.phrases else None

    async def run_turn(
        self,
        *,
        user_text: str,
        conversation_id: UUID | None = None,
        user_id: str | None = None,
    ) -> AsyncIterator[Event]:
        conv = (
            await self._convs.get(conversation_id)
            if conversation_id else None
        )
        if conv is None:
            conv = await self._convs.create(
                agent_id=self._cfg.agent_id,
                system_prompt=self._cfg.system_prompt,
                provider=self._cfg.provider,
                model=self._cfg.model,
                user_id=user_id,
            )

        tracer = TraceLogger(self._traces, conv.id, enabled=self._cfg.tracing.enabled)
        await tracer.event("request_received", metadata={"chars": len(user_text)})

        await self._msgs.append(
            conversation_id=conv.id,
            role="user",
            kind="user_text",
            content=user_text,
        )

        if self._ack and self._cfg.ack.enabled:
            ack_text = self._ack.pick()
            ack_t0 = time.monotonic()
            ack_msg = await self._msgs.append(
                conversation_id=conv.id,
                role="assistant",
                kind="ack",
                content=ack_text,
            )
            yield AckEvent(text=ack_text)
            await tracer.span(
                "ack_sent",
                latency_ms=int((time.monotonic() - ack_t0) * 1000),
                message_id=ack_msg.id,
            )

        history = await self._msgs.recent(conv.id, limit=self._cfg.history_limit)
        provider_msgs = build_messages(history)
        system = build_system_prompt(self._cfg.system_prompt)
        tool_specs = self._tools.for_groups(self._cfg.tool_groups)
        if self._cfg.subagents.enabled:
            tool_specs = [
                *tool_specs,
                make_delegation_tool(
                    llm=self._llm,
                    system_prompt=system,
                    parent_messages=provider_msgs,
                    worker_tools=tool_specs,
                    model=self._cfg.model,
                    temperature=self._cfg.temperature,
                    max_tokens=self._cfg.max_tokens,
                    thinking_enabled=self._cfg.thinking_enabled,
                    settings=SubagentSettings(
                        max_children=self._cfg.subagents.max_children,
                        max_iters=self._cfg.subagents.max_iters,
                        timeout_s=self._cfg.subagents.timeout_s,
                        tool_timeout_s=self._cfg.timeouts.tool_s,
                    ),
                ),
            ]
        tool_schemas = [t.to_provider_schema() for t in tool_specs]
        await tracer.event(
            "context_built",
            metadata={
                "history_count": len(history),
                "context_msgs": len(provider_msgs),
                "tools": [t.name for t in tool_specs],
            },
        )

        final_assistant_msg_id: UUID | None = None
        try:
            async for ev in self._llm_loop(
                conv_id=conv.id,
                system=system,
                provider_msgs=provider_msgs,
                tool_specs={t.name: t for t in tool_specs},
                tool_schemas=tool_schemas,
                tracer=tracer,
            ):
                if isinstance(ev, _FinalMessageMarker):
                    final_assistant_msg_id = ev.message_id
                    continue
                yield ev
        except ProviderError as e:
            log.exception("runtime: provider error")
            await self._msgs.append(
                conversation_id=conv.id,
                role="assistant",
                kind="error",
                content=_PROVIDER_ERROR_MESSAGE,
                content_json={"kind": "provider", "detail": str(e)},
            )
            yield ErrorEvent(
                kind="provider",
                message=_PROVIDER_ERROR_MESSAGE,
                metadata={"detail": str(e)},
            )
        except Exception as e:
            log.exception("runtime: unexpected error")
            await self._msgs.append(
                conversation_id=conv.id,
                role="assistant",
                kind="error",
                content=_INTERNAL_ERROR_MESSAGE,
                content_json={"kind": "internal", "detail": str(e)},
            )
            yield ErrorEvent(
                kind="internal",
                message=_INTERNAL_ERROR_MESSAGE,
                metadata={"detail": str(e)},
            )

        await self._convs.touch(conv.id)
        await tracer.event("done", message_id=final_assistant_msg_id)
        yield DoneEvent(
            conversation_id=conv.id,
            message_id=final_assistant_msg_id,
            total_ms=tracer.total_ms,
        )

    async def _llm_loop(
        self,
        *,
        conv_id: UUID,
        system: str,
        provider_msgs: list[ProviderMessage],
        tool_specs: dict[str, ToolSpec],
        tool_schemas: list,
        tracer: TraceLogger,
    ) -> AsyncIterator[Event]:
        """Runs LLM streaming + tool dispatch until the model says stop.

        Emits TextDelta / ThinkingDelta / ToolStart / ToolEnd / ErrorEvent. Sends a single
        `_FinalMessageMarker` carrying the persisted assistant message id
        when the assistant text is finalized.
        """
        max_iters = 8
        for iteration in range(max_iters):
            text_buf: list[str] = []
            pending_calls: list[LLMToolCall] = []
            finish_reason: str = "stop"
            llm_t0 = time.monotonic()
            first_token_seen = False

            await tracer.event(
                "llm_call_started",
                metadata={"iteration": iteration, "msgs": len(provider_msgs)},
            )

            stream = self._llm.stream(
                system=system,
                messages=provider_msgs,
                tools=tool_schemas,
                model=self._cfg.model,
                temperature=self._cfg.temperature,
                max_tokens=self._cfg.max_tokens,
                thinking_enabled=self._cfg.thinking_enabled,
            )

            async for ev in stream:
                if isinstance(ev, LLMTextDelta):
                    if not first_token_seen:
                        first_token_seen = True
                        await tracer.span(
                            "llm_first_token",
                            latency_ms=int((time.monotonic() - llm_t0) * 1000),
                        )
                    text_buf.append(ev.text)
                    yield TextDelta(text=ev.text)
                elif isinstance(ev, LLMThinkingDelta):
                    if not first_token_seen:
                        first_token_seen = True
                        await tracer.span(
                            "llm_first_token",
                            latency_ms=int((time.monotonic() - llm_t0) * 1000),
                        )
                    yield ThinkingDelta(text=ev.text)
                elif isinstance(ev, LLMToolCall):
                    pending_calls.append(ev)
                elif isinstance(ev, LLMFinish):
                    finish_reason = ev.reason
                elif isinstance(ev, LLMError):
                    yield ErrorEvent(
                        kind="provider_stream",
                        message=_PROVIDER_ERROR_MESSAGE,
                        metadata={"detail": ev.message},
                    )
                    finish_reason = "error"

            assistant_text = "".join(text_buf)
            assistant_msg_id: UUID | None = None
            if assistant_text:
                msg = await self._msgs.append(
                    conversation_id=conv_id,
                    role="assistant",
                    kind="assistant_text",
                    content=_truncate(assistant_text),
                    latency_ms=int((time.monotonic() - llm_t0) * 1000),
                    metadata={"iteration": iteration},
                )
                assistant_msg_id = msg.id

            if not pending_calls:
                await tracer.span(
                    "assistant_completed",
                    latency_ms=int((time.monotonic() - llm_t0) * 1000),
                    message_id=assistant_msg_id,
                    metadata={"reason": finish_reason},
                )
                yield _FinalMessageMarker(message_id=assistant_msg_id)
                return

            provider_msgs.append(ProviderMessage(
                role="assistant",
                content=assistant_text or None,
                tool_calls=[
                    ProviderToolCall(call_id=c.call_id, name=c.name, args=c.args)
                    for c in pending_calls
                ],
            ))

            for call in pending_calls:
                tool_result = await self._dispatch_tool(
                    conv_id=conv_id,
                    call=call,
                    tool_specs=tool_specs,
                    tracer=tracer,
                )
                yield tool_result.start_event
                yield tool_result.end_event
                provider_msgs.append(ProviderMessage(
                    role="tool",
                    content=tool_result.content_for_llm,
                    tool_call_id=call.call_id,
                ))

        log.warning("runtime: hit max_iters=%d, breaking", max_iters)
        yield ErrorEvent(kind="loop_limit", message="agent exceeded max tool iterations")
        yield _FinalMessageMarker(message_id=None)

    async def _dispatch_tool(
        self,
        *,
        conv_id: UUID,
        call: LLMToolCall,
        tool_specs: dict[str, ToolSpec],
        tracer: TraceLogger,
    ) -> _DispatchedTool:
        spec = tool_specs.get(call.name)
        ctx_meta = {"args": call.args}
        await self._msgs.append(
            conversation_id=conv_id,
            role="assistant",
            kind="tool_call",
            tool_name=call.name,
            tool_call_id=call.call_id,
            content_json=ctx_meta,
        )
        await tracer.event(
            "tool_started",
            metadata={"tool": call.name, "call_id": call.call_id},
        )
        start = ToolStart(
            tool_name=call.name,
            args=call.args,
            call_id=call.call_id,
            server=spec.server if spec else None,
        )

        t0 = time.monotonic()
        if spec is None:
            err = f"unknown tool: {call.name}"
            await self._msgs.append(
                conversation_id=conv_id,
                role="tool",
                kind="tool_result",
                tool_name=call.name,
                tool_call_id=call.call_id,
                content=err,
                content_json={"error": err},
                latency_ms=0,
            )
            return _DispatchedTool(
                start_event=start,
                end_event=ToolEnd(
                    call_id=call.call_id, tool_name=call.name,
                    ok=False, latency_ms=0, error=err,
                ),
                content_for_llm=err,
            )

        try:
            args = validate_args(spec, call.args)
        except ToolValidationError as e:
            latency = int((time.monotonic() - t0) * 1000)
            content = f"Invalid arguments: {e}"
            await self._msgs.append(
                conversation_id=conv_id,
                role="tool",
                kind="tool_result",
                tool_name=call.name,
                tool_call_id=call.call_id,
                content=content,
                content_json={"validation_error": str(e)},
                latency_ms=latency,
            )
            await tracer.span(
                "tool_completed", latency_ms=latency,
                metadata={"tool": call.name, "ok": False, "kind": "validation"},
            )
            return _DispatchedTool(
                start_event=start,
                end_event=ToolEnd(
                    call_id=call.call_id, tool_name=call.name,
                    ok=False, latency_ms=latency, error=content,
                ),
                content_for_llm=content,
            )

        ctx = ToolContext(conversation_id=str(conv_id), call_id=call.call_id)
        try:
            result: ToolResult = await asyncio.wait_for(
                spec.handler(args, ctx),
                timeout=spec.timeout_s or self._cfg.timeouts.tool_s,
            )
            ok = True
            error: str | None = None
            content_for_llm = result.output
            summary = result.summary or _short(result.output)
            content_json: dict[str, Any] = {"summary": summary, **result.metadata}
        except asyncio.TimeoutError:
            ok = False
            timeout_s = spec.timeout_s or self._cfg.timeouts.tool_s
            error = f"tool {call.name} timed out after {timeout_s}s"
            content_for_llm = error
            content_json = {"error": error}
            summary = error
        except ToolError as e:
            ok = False
            error = str(e)
            content_for_llm = f"Tool error: {error}"
            content_json = {"error": error}
            summary = error
        except Exception as e:
            log.exception("runtime: tool handler raised: %s", call.name)
            ok = False
            error = f"{type(e).__name__}: {e}"
            content_for_llm = f"Tool error: {error}"
            content_json = {"error": error}
            summary = error

        latency = int((time.monotonic() - t0) * 1000)
        await self._msgs.append(
            conversation_id=conv_id,
            role="tool",
            kind="tool_result",
            tool_name=call.name,
            tool_call_id=call.call_id,
            content=_truncate(content_for_llm),
            content_json=content_json,
            latency_ms=latency,
        )
        await tracer.span(
            "tool_completed",
            latency_ms=latency,
            metadata={"tool": call.name, "ok": ok},
        )
        return _DispatchedTool(
            start_event=start,
            end_event=ToolEnd(
                call_id=call.call_id, tool_name=call.name,
                ok=ok, latency_ms=latency, summary=summary, error=error,
            ),
            content_for_llm=_truncate(content_for_llm),
        )


class _DispatchedTool:
    __slots__ = ("start_event", "end_event", "content_for_llm")

    def __init__(self, *, start_event: ToolStart, end_event: ToolEnd, content_for_llm: str) -> None:
        self.start_event = start_event
        self.end_event = end_event
        self.content_for_llm = content_for_llm


class _FinalMessageMarker:
    """Internal sentinel — never yielded to callers."""
    __slots__ = ("message_id",)

    def __init__(self, message_id: UUID | None) -> None:
        self.message_id = message_id


def _truncate(text: str, *, cap: int = _CONTENT_INLINE_CAP) -> str:
    if len(text.encode("utf-8")) <= cap:
        return text
    return text[: cap // 2] + "\n…[truncated]…"


def _short(text: str, *, limit: int = 200) -> str:
    text = text.strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


# Re-exported for type-checking convenience.
__all__ = ["AgentRuntime"]


def _coerce_json(value: Any) -> Any:
    """Helper kept for callers that need to serialize tool args defensively."""
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)
