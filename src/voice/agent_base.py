from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Union


@dataclass
class TokenEvent:
    text: str


@dataclass
class TurnEndEvent:
    """Agent has finished its turn and is waiting for user input."""

    info: dict[str, Any] = field(default_factory=dict)


@dataclass
class DoneEvent:
    """Conversation is complete; no further turns expected."""

    info: dict[str, Any] = field(default_factory=dict)


AgentEvent = Union[TokenEvent, TurnEndEvent, DoneEvent]


class AgentBackend(ABC):
    """A swappable conversational agent.

    The voice pipeline only requires that a backend can:
      - be started with arbitrary opaque params,
      - be resumed with a user utterance (text),
      - stream `TokenEvent`s during its turns,
      - emit a `TurnEndEvent` when the floor passes back to the user,
      - emit a `DoneEvent` when the conversation is over.
    """

    @abstractmethod
    def start(self, params: dict[str, Any]) -> AsyncIterator[AgentEvent]: ...

    @abstractmethod
    def resume(self, user_text: str) -> AsyncIterator[AgentEvent]: ...

    async def close(self) -> None:
        return None
