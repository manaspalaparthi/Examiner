from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

from agent.events import AckEvent, DoneEvent as RuntimeDoneEvent, ErrorEvent, Event, TextDelta
from voice.agent_base import TokenEvent, TurnEndEvent
from voice.agent_runtime import RuntimeAgent


def test_runtime_done_means_voice_turn_end() -> None:
    conv_id = uuid4()
    msg_id = uuid4()
    agent = RuntimeAgent(greeting=None)
    agent._runtime = _FakeRuntime(  # type: ignore[assignment]
        [
            AckEvent("One sec."),
            TextDelta("Hello "),
            TextDelta("there."),
            RuntimeDoneEvent(conversation_id=conv_id, message_id=msg_id, total_ms=123),
        ]
    )

    events = asyncio.run(_collect(agent.resume("hi")))

    assert [type(event) for event in events] == [
        TokenEvent,
        TokenEvent,
        TokenEvent,
        TurnEndEvent,
    ]
    assert [event.text for event in events[:3]] == ["One sec.", "Hello ", "there."]
    assert events[-1].info == {
        "conversation_id": str(conv_id),
        "message_id": str(msg_id),
        "total_ms": 123,
    }


def test_runtime_start_can_greet_without_llm_turn() -> None:
    agent = _ReadyRuntimeAgent(greeting="Ready.")

    events = asyncio.run(_collect(agent.start({})))

    assert events == [
        TokenEvent("Ready."),
        TurnEndEvent(info={"conversation_id": None}),
    ]


def test_provider_errors_are_spoken_without_raw_details() -> None:
    conv_id = uuid4()
    raw_error = (
        "gemini request failed: 500 INTERNAL. "
        "{'error': {'message': 'Internal error encountered.'}}"
    )
    agent = RuntimeAgent(greeting=None)
    agent._runtime = _FakeRuntime(  # type: ignore[assignment]
        [
            ErrorEvent(kind="provider", message=raw_error),
            RuntimeDoneEvent(conversation_id=conv_id, message_id=None, total_ms=9),
        ]
    )

    events = asyncio.run(_collect(agent.resume("hi")))

    assert events[0] == TokenEvent(
        "The model provider is having trouble right now. Please try again in a moment."
    )
    assert raw_error not in events[0].text


class _FakeRuntime:
    def __init__(self, events: list[Event]) -> None:
        self._events = events

    async def run_turn(self, **kwargs) -> AsyncIterator[Event]:  # noqa: ANN003, ARG002
        for event in self._events:
            yield event


class _ReadyRuntimeAgent(RuntimeAgent):
    async def _ensure_runtime(self) -> None:
        self._runtime = _FakeRuntime([])


async def _collect(events: AsyncIterator) -> list:
    return [event async for event in events]
