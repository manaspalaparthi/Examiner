from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Union
from uuid import UUID


@dataclass
class AckEvent:
    text: str


@dataclass
class TextDelta:
    text: str


@dataclass
class ThinkingDelta:
    text: str


@dataclass
class ToolStart:
    tool_name: str
    args: dict[str, Any]
    call_id: str
    server: str | None = None


@dataclass
class ToolEnd:
    call_id: str
    tool_name: str
    ok: bool
    latency_ms: int
    summary: str | None = None
    error: str | None = None


@dataclass
class ErrorEvent:
    kind: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DoneEvent:
    conversation_id: UUID
    message_id: UUID | None
    total_ms: int


Event = Union[AckEvent, TextDelta, ThinkingDelta, ToolStart, ToolEnd, ErrorEvent, DoneEvent]
