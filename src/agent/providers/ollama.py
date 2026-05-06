from __future__ import annotations

import json
import logging
import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx

from ..errors import ProviderError
from .base import (
    LLMClient,
    LLMError,
    LLMFinish,
    LLMThinkingDelta,
    LLMTextDelta,
    LLMToolCall,
    ProviderEvent,
    ProviderMessage,
    ToolSchema,
)

log = logging.getLogger(__name__)


class OllamaClient(LLMClient):
    """Streams from Ollama's /api/chat as NDJSON.

    Tool-call format follows Ollama's OpenAI-compatible `tool_calls` array on
    assistant messages. For non-tool models, the LLM simply never emits tool
    calls and the runtime falls through to plain text replies.
    """

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout_s: float = 120.0,
    ) -> None:
        self._base_url = (base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout_s)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def stream(
        self,
        *,
        system: str,
        messages: list[ProviderMessage],
        tools: list[ToolSchema],
        model: str,
        temperature: float = 0.3,
        max_tokens: int | None = None,
        thinking_enabled: bool = True,
    ) -> AsyncIterator[ProviderEvent]:
        body: dict[str, Any] = {
            "model": model,
            "stream": True,
            "messages": _to_ollama_messages(system, messages),
            "options": {"temperature": temperature},
            "think": thinking_enabled,
        }
        if max_tokens is not None:
            body["options"]["num_predict"] = max_tokens
        if tools:
            body["tools"] = [_to_ollama_tool(t) for t in tools]

        url = f"{self._base_url}/api/chat"
        in_thinking = False
        try:
            async with self._client.stream("POST", url, json=body) as resp:
                if resp.status_code >= 400:
                    text = (await resp.aread()).decode("utf-8", errors="replace")
                    yield LLMError(f"ollama {resp.status_code}: {text[:400]}")
                    yield LLMFinish(reason="error")
                    return
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        log.warning("ollama: skipping non-JSON line: %s", line[:200])
                        continue
                    msg = chunk.get("message") or {}
                    thinking = msg.get("thinking")
                    if thinking and thinking_enabled:
                        yield LLMThinkingDelta(text=thinking)
                    text = msg.get("content")
                    if text:
                        pieces, in_thinking = _split_thinking_markup(text, in_thinking)
                        for kind, piece in pieces:
                            if not piece:
                                continue
                            if kind == "thinking":
                                if thinking_enabled:
                                    yield LLMThinkingDelta(text=piece)
                            else:
                                yield LLMTextDelta(text=piece)
                    for tc in msg.get("tool_calls") or []:
                        fn = tc.get("function") or {}
                        name = fn.get("name", "")
                        args = fn.get("arguments") or {}
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = {"_raw": args}
                        yield LLMToolCall(
                            call_id=tc.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                            name=name,
                            args=args,
                        )
                    if chunk.get("done"):
                        reason = "tool_calls" if msg.get("tool_calls") else "stop"
                        yield LLMFinish(reason=reason)
                        return
        except httpx.HTTPError as e:
            raise ProviderError(f"ollama request failed: {e}") from e


def _to_ollama_messages(system: str, messages: list[ProviderMessage]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if system:
        out.append({"role": "system", "content": system})
    for m in messages:
        if m.role == "tool":
            out.append({
                "role": "tool",
                "content": m.content or "",
                "tool_call_id": m.tool_call_id or "",
            })
            continue
        msg: dict[str, Any] = {"role": m.role, "content": m.content or ""}
        if m.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.call_id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.args},
                }
                for tc in m.tool_calls
            ]
        out.append(msg)
    return out


def _to_ollama_tool(t: ToolSchema) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": t.name,
            "description": t.description,
            "parameters": t.parameters,
        },
    }


def _split_thinking_markup(text: str, in_thinking: bool) -> tuple[list[tuple[str, str]], bool]:
    """Split common <think>...</think> model output into hidden reasoning chunks."""
    parts: list[tuple[str, str]] = []
    cursor = 0
    mode = "thinking" if in_thinking else "text"
    while cursor < len(text):
        marker = "</think>" if mode == "thinking" else "<think>"
        idx = text.find(marker, cursor)
        if idx == -1:
            parts.append((mode, text[cursor:]))
            break
        parts.append((mode, text[cursor:idx]))
        cursor = idx + len(marker)
        mode = "text" if mode == "thinking" else "thinking"
    return parts, mode == "thinking"
