from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from voice.agent_base import TokenEvent, TurnEndEvent
from voice.session import VoiceSession


def test_voice_session_keeps_markdown_for_ui_and_normalizes_tts() -> None:
    ws = _FakeWebSocket()
    tts = _FakeTTS()
    session = VoiceSession(
        ws=ws,
        vad=_FakeVAD(),
        stt=object(),
        tts=tts,
        agent=object(),
        initial_params={},
    )

    asyncio.run(session._run_agent_turn(_events([TokenEvent("Try **Apples** at 50%."), TurnEndEvent()])))

    assert {"type": "agent_text", "text": "Try **Apples** at 50%."} in ws.sent_json
    assert tts.texts == ["Try Apples at 50%."]


async def _events(items: list[object]) -> AsyncIterator[object]:
    for item in items:
        yield item


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent_json: list[dict] = []

    async def send_text(self, text: str) -> None:
        self.sent_json.append(json.loads(text))


class _FakeVAD:
    def unmute(self) -> None:
        return None


class _FakeTTS:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def synth(self, text: str, **kwargs) -> AsyncIterator[bytes]:  # noqa: ANN003, ARG002
        self.texts.append(text)
        yield b"audio"
