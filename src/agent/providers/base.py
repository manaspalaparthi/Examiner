from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, Union, runtime_checkable


@dataclass
class ProviderMessage:
    """A normalized message in the LLM context.

    `role` is one of: system, user, assistant, tool.
    `content` is plain text for user/assistant/system. For tool messages it
    holds the tool result text/JSON; `tool_call_id` ties it back to the
    assistant's preceding tool_call.
    `tool_calls` (assistant only) carries any tool calls the assistant
    decided on this turn so they can be replayed back to the provider.
    """

    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[ProviderToolCall] = field(default_factory=list)
    tool_call_id: str | None = None


@dataclass
class ProviderToolCall:
    call_id: str
    name: str
    args: dict[str, Any]


@dataclass
class ToolSchema:
    """Provider-agnostic tool schema. Adapters convert to native form."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class LLMTextDelta:
    text: str


@dataclass
class LLMThinkingDelta:
    text: str


@dataclass
class LLMToolCall:
    call_id: str
    name: str
    args: dict[str, Any]


@dataclass
class LLMFinish:
    reason: Literal["stop", "tool_calls", "length", "error"]


@dataclass
class LLMError:
    message: str


ProviderEvent = Union[LLMTextDelta, LLMThinkingDelta, LLMToolCall, LLMFinish, LLMError]


@runtime_checkable
class LLMClient(Protocol):
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
    ) -> AsyncIterator[ProviderEvent]: ...

    async def aclose(self) -> None: ...
