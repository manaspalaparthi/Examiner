from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from typing import Any

from langgraph_sdk import get_client

from .agent_base import AgentBackend, AgentEvent, DoneEvent, TokenEvent, TurnEndEvent

log = logging.getLogger(__name__)


class LangGraphAgent(AgentBackend):
    """Bridges to any graph served by `langgraph dev` / langgraph-server.

    Generic over `assistant_id`; the existing examiner graph is just one
    deployment. Token streaming uses `stream_mode=["messages","updates"]`
    so we get per-token AIMessageChunks plus the `__interrupt__` marker
    that signals the agent is waiting for user input.
    """

    def __init__(
        self,
        assistant_id: str,
        base_url: str | None = None,
    ) -> None:
        self._assistant_id = assistant_id
        self._url = base_url or os.environ.get("LANGGRAPH_URL", "http://localhost:2024")
        self._client = get_client(url=self._url)
        self._thread_id: str | None = None

    async def _ensure_thread(self) -> str:
        if self._thread_id is None:
            thread = await self._client.threads.create()
            self._thread_id = thread["thread_id"]
        return self._thread_id

    async def start(self, params: dict[str, Any]) -> AsyncIterator[AgentEvent]:
        thread_id = await self._ensure_thread()
        async for ev in self._stream(thread_id, input=params):
            yield ev

    async def resume(self, user_text: str) -> AsyncIterator[AgentEvent]:
        thread_id = await self._ensure_thread()
        async for ev in self._stream(thread_id, command={"resume": user_text}):
            yield ev

    async def _stream(self, thread_id: str, **kwargs: Any) -> AsyncIterator[AgentEvent]:
        saw_interrupt = False
        chunks_seen = 0
        tokens_emitted = 0
        # Per-stream buffers for two pieces of context that span chunks:
        # - `assistant_text` is the running concatenation of speakable text
        #   in *this* run, used to detect the `<report>` terminator.
        # - `report_open` flips true the first time we see `<report>` and
        #   suppresses all further TokenEvents (the report is markdown and
        #   sounds awful when TTS'd; the UI still gets the `agent_text`
        #   event from session.py for on-screen rendering).
        assistant_text = ""
        report_open = False
        log.info("agent: streaming thread=%s assistant=%s kwargs_keys=%s",
                 thread_id, self._assistant_id, list(kwargs))
        async for chunk in self._client.runs.stream(
            thread_id,
            assistant_id=self._assistant_id,
            stream_mode=["messages", "updates"],
            **kwargs,
        ):
            chunks_seen += 1
            preview = repr(chunk.data)[:1200] if chunk.data is not None else "None"
            log.debug("agent: chunk #%d event=%s data=%s",
                      chunks_seen, chunk.event, preview)
            if chunk.event in ("messages", "messages/partial", "messages/complete"):
                # Temporary diagnostic: dump the first few messages chunks at
                # INFO so we can see the actual shape coming back from the SDK.
                # Remove once token extraction is confirmed working.
                if chunks_seen <= 5:
                    log.info("agent: messages chunk #%d data=%s",
                             chunks_seen, preview[:800])
                text = _extract_ai_token(chunk.data)
                if not text:
                    continue
                assistant_text += text
                if not report_open and "<report>" in assistant_text:
                    report_open = True
                if report_open:
                    continue
                tokens_emitted += 1
                yield TokenEvent(text=text)
            elif chunk.event == "updates":
                interrupt = _extract_interrupt(chunk.data)
                if interrupt is not None:
                    saw_interrupt = True
                    yield TurnEndEvent(info=interrupt)
            elif chunk.event == "error":
                log.error("agent: langgraph stream returned error: %s", chunk.data)
        log.info("agent: stream ended chunks=%d tokens=%d interrupt=%s report=%s",
                 chunks_seen, tokens_emitted, saw_interrupt, report_open)
        if saw_interrupt:
            return
        if report_open:
            yield DoneEvent()
        else:
            yield TurnEndEvent()


_SPEAKABLE_BLOCK_TYPES = {None, "text"}
_SILENT_BLOCK_TYPES = {"thinking", "reasoning", "tool_use", "tool_call"}


def _extract_ai_token(data: Any) -> str:
    """Pull speakable text out of an AIMessageChunk frame.

    Skips tool messages, thinking/reasoning blocks (internal monologue),
    and tool-call blocks. Only `text` blocks (or plain string content)
    are forwarded to TTS.
    """
    if not isinstance(data, list) or not data:
        return ""
    msg = data[0]
    if not isinstance(msg, dict):
        return ""
    if msg.get("type") not in (None, "AIMessageChunk", "ai"):
        return ""
    content = msg.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype in _SPEAKABLE_BLOCK_TYPES:
                t = block.get("text", "")
                if isinstance(t, str):
                    parts.append(t)
            elif btype in _SILENT_BLOCK_TYPES:
                continue
            else:
                # Unknown block type — log once for visibility, skip.
                log.debug("agent: skipping unknown content block type %r", btype)
        return "".join(parts)
    return ""


def _extract_interrupt(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    interrupts = data.get("__interrupt__")
    if not interrupts:
        return None
    first = interrupts[0]
    if isinstance(first, dict):
        value = first.get("value", first)
        return value if isinstance(value, dict) else {"value": value}
    return {"value": first}
