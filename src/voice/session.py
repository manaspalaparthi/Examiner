from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

import numpy as np
from fastapi import WebSocket, WebSocketDisconnect

from .agent_base import AgentBackend, DoneEvent, TokenEvent, TurnEndEvent
from .sentencizer import sentencize
from .speech_normalizer import normalize_for_speech

if TYPE_CHECKING:
    from .stt import ParakeetSTT
    from .tts import KokoroTTS
    from .vad import SileroVAD

log = logging.getLogger(__name__)


class State(str, Enum):
    THINKING = "thinking"
    SPEAKING = "speaking"
    LISTENING = "listening"


class VoiceSession:
    """Per-WebSocket orchestrator.

    Wires VAD → STT → AgentBackend → sentencizer → TTS, and is agnostic
    to which agent backend is plugged in — anything implementing
    `AgentBackend` works the same way.
    """

    def __init__(
        self,
        ws: WebSocket,
        vad: SileroVAD,
        stt: ParakeetSTT,
        tts: KokoroTTS,
        agent: AgentBackend,
        initial_params: dict[str, Any],
        tts_options: dict[str, Any] | None = None,
        echo_tail_s: float | None = None,
        barge_in_enabled: bool = True,
        barge_in_min_speech_ms: int | None = None,
        barge_in_min_rms: float | None = None,
    ) -> None:
        self._ws = ws
        self._vad = vad
        self._stt = stt
        self._tts = tts
        self._tts_options = tts_options or {}
        self._agent = agent
        self._initial_params = initial_params

        self._utterance_q: asyncio.Queue[np.ndarray] = asyncio.Queue()
        self._barge_in_q: asyncio.Queue[None] = asyncio.Queue(maxsize=1)
        self._frame_q: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._done = asyncio.Event()
        self._state = State.THINKING
        # Tail delay before re-opening the mic, to let the client finish
        # playing buffered TTS audio so the user's mic doesn't pick up the
        # tail of our own speech (echo / self-listening).
        self._echo_tail_s = (
            echo_tail_s
            if echo_tail_s is not None
            else float(os.environ.get("VOICE_ECHO_TAIL_S", "0.7"))
        )
        self._barge_in_enabled = barge_in_enabled
        self._barge_in_min_speech_ms = (
            barge_in_min_speech_ms
            if barge_in_min_speech_ms is not None
            else int(os.environ.get("VOICE_BARGE_IN_MIN_SPEECH_MS", "420"))
        )
        self._barge_in_min_rms = (
            barge_in_min_rms
            if barge_in_min_rms is not None
            else float(os.environ.get("VOICE_BARGE_IN_MIN_RMS", "0.012"))
        )

    async def run(self) -> None:
        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self._audio_in_loop(), name="audio_in")
                tg.create_task(self._frame_out_loop(), name="frame_out")
                tg.create_task(self._conversation_loop(), name="conversation")
        except* WebSocketDisconnect:
            log.info("session: client disconnected")
        except* Exception as eg:
            for exc in eg.exceptions:
                log.exception("session: task failed", exc_info=exc)
        finally:
            await self._agent.close()

    # ---------- IO loops ----------

    async def _audio_in_loop(self) -> None:
        """Receive mic frames from the client; feed VAD; emit utterances."""
        try:
            while not self._done.is_set():
                msg = await self._ws.receive()
                if msg["type"] == "websocket.disconnect":
                    raise WebSocketDisconnect(code=msg.get("code", 1000))
                data = msg.get("bytes")
                if data is None:
                    text = msg.get("text")
                    if text:
                        log.debug("session: ignoring text frame mid-session: %s", text[:80])
                    continue
                was_in_speech = self._vad.in_speech
                for utt in self._vad.feed(data):
                    await self._utterance_q.put(utt)
                if self._should_barge_in(was_in_speech):
                    await self._barge_in_q.put(None)
        except WebSocketDisconnect:
            self._done.set()
            raise

    async def _frame_out_loop(self) -> None:
        """Drain TTS frames to the WebSocket as fast as the socket accepts them."""
        while True:
            frame = await self._frame_q.get()
            if frame is None:
                return
            try:
                await self._ws.send_bytes(frame)
            except WebSocketDisconnect:
                self._done.set()
                return

    # ---------- Conversation orchestration ----------

    async def _conversation_loop(self) -> None:
        try:
            # First turn: agent introduces itself / asks first question.
            result = await self._run_agent_turn(self._agent.start(self._initial_params))
            while not self._done.is_set():
                if result.done:
                    await self._send_json({"type": "done"})
                    self._done.set()
                    return
                if result.interrupted_text:
                    result = await self._run_agent_turn(
                        self._agent.resume(_interruption_prompt(result.interrupted_text))
                    )
                    continue

                # Yield the floor to the user, but only after the client has
                # finished playing our queued audio — otherwise the mic will
                # pick up the tail of our own TTS.
                await self._wait_for_playback_drain()
                self._state = State.LISTENING
                self._vad.unmute()
                await self._send_json({"type": "listening"})

                utt = await self._utterance_q.get()
                self._vad.mute()
                self._state = State.THINKING

                text = await self._stt.transcribe(utt)
                if not text:
                    log.info("session: empty transcript, re-listening")
                    continue
                await self._send_json({"type": "transcript", "text": text})
                result = await self._run_agent_turn(self._agent.resume(text))
        finally:
            await self._frame_q.put(None)
            self._done.set()

    async def _run_agent_turn(self, events: AsyncIterator) -> "_TurnResult":
        """Stream one agent turn: tokens → sentences → TTS frames → WS."""
        self._drain_barge_in()
        self._vad.unmute()
        self._state = State.SPEAKING
        token_q: asyncio.Queue[str | None] = asyncio.Queue()
        agent_done = asyncio.Event()
        turn_result = _TurnResult()
        sent_speaking_ended = False

        async def token_iter() -> AsyncIterator[str]:
            while True:
                t = await token_q.get()
                if t is None:
                    return
                yield t

        speaking_started = False

        async def tts_pump() -> None:
            nonlocal speaking_started
            async for sentence in sentencize(token_iter()):
                if not speaking_started:
                    await self._send_json({"type": "speaking_started"})
                    speaking_started = True
                await self._send_json({"type": "agent_text", "text": sentence})
                speech_sentence = normalize_for_speech(sentence)
                if not speech_sentence:
                    continue
                async for frame in self._tts.synth(speech_sentence, **self._tts_options):
                    await self._frame_q.put(frame)

        async def agent_pump() -> None:
            try:
                async for event in events:
                    if isinstance(event, TokenEvent):
                        await token_q.put(event.text)
                    elif isinstance(event, TurnEndEvent):
                        # Some agents (e.g. the examiner's `ask_candidate` tool)
                        # carry the user-facing utterance in the interrupt payload
                        # rather than the message stream. Pull it out and speak it.
                        turn_result.info = event.info
                        speech = _extract_speech(event.info)
                        if speech:
                            await token_q.put(speech)
                        break
                    elif isinstance(event, DoneEvent):
                        turn_result.done = True
                        break
            finally:
                agent_done.set()
                await token_q.put(None)

        tts_task = asyncio.create_task(tts_pump(), name="tts_pump")
        agent_task = asyncio.create_task(agent_pump(), name="agent_pump")
        barge_task = asyncio.create_task(self._barge_in_q.get(), name="barge_in_wait")
        try:
            done, _ = await asyncio.wait(
                {tts_task, barge_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if barge_task in done and not tts_task.done():
                log.info("session: barge-in detected; stopping agent speech")
                agent_task.cancel()
                tts_task.cancel()
                await token_q.put(None)
                self._clear_frame_queue()
                await self._send_json({"type": "interrupted"})
                if speaking_started:
                    await self._send_json({"type": "speaking_ended", "interrupted": True})
                    sent_speaking_ended = True

                utt = await self._utterance_q.get()
                text = await self._stt.transcribe(utt)
                if text:
                    turn_result.interrupted_text = text
                    await self._send_json({"type": "transcript", "text": text, "interrupted": True})
                else:
                    log.info("session: barge-in transcript was empty")
                return turn_result
        finally:
            if not barge_task.done():
                barge_task.cancel()
            if not agent_task.done():
                agent_task.cancel()
            try:
                await agent_task
            except asyncio.CancelledError:
                pass
            try:
                await tts_task
            except asyncio.CancelledError:
                pass
            if speaking_started and not sent_speaking_ended:
                await self._send_json({"type": "speaking_ended"})

        if turn_result.info is not None:
            await self._send_json(_turn_end_payload(turn_result.info))
        return turn_result

    async def _wait_for_playback_drain(self) -> None:
        """Block until the outbound frame queue is empty + an echo-tail delay.

        The frame queue draining only means we've handed all bytes to the
        WebSocket; the client still has its own jitter buffer + OS audio
        buffer that take a few hundred ms to play out. We can't observe
        that directly, so add a fixed tail (`VOICE_ECHO_TAIL_S`).
        """
        while not self._frame_q.empty():
            await asyncio.sleep(0.02)
        if self._echo_tail_s > 0:
            await asyncio.sleep(self._echo_tail_s)

    async def _send_json(self, payload: dict[str, Any]) -> None:
        try:
            await self._ws.send_text(json.dumps(payload))
        except WebSocketDisconnect:
            self._done.set()

    def _clear_frame_queue(self) -> None:
        while True:
            try:
                self._frame_q.get_nowait()
            except asyncio.QueueEmpty:
                return

    def _drain_barge_in(self) -> None:
        while True:
            try:
                self._barge_in_q.get_nowait()
            except asyncio.QueueEmpty:
                return

    def _should_barge_in(self, was_in_speech: bool) -> bool:
        if not self._barge_in_enabled:
            return False
        if self._state is not State.SPEAKING:
            return False
        if self._barge_in_q.full():
            return False
        if was_in_speech and self._vad.speech_duration_ms < self._barge_in_min_speech_ms:
            return False
        if not self._vad.in_speech:
            return False
        if self._vad.speech_duration_ms < self._barge_in_min_speech_ms:
            return False
        if self._vad.speech_rms < self._barge_in_min_rms:
            return False
        return True


@dataclass
class _TurnResult:
    done: bool = False
    interrupted_text: str | None = None
    info: dict[str, Any] | None = None


def _turn_end_payload(info: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "turn_end",
        "conversationId": info.get("conversation_id"),
        "messageId": info.get("message_id"),
        "totalMs": info.get("total_ms"),
    }


def _extract_speech(info: dict[str, Any] | None) -> str | None:
    """Pull a speakable string out of an interrupt payload.

    Backends use different conventions: the examiner agent emits
    ``{"type": "question", "question": "..."}``; others may use ``text``
    or a nested ``value``. Probe in order; bail to None if nothing fits.
    """
    if not info:
        return None
    for key in ("question", "text", "prompt", "message"):
        v = info.get(key)
        if isinstance(v, str) and v.strip():
            return v
    nested = info.get("value")
    if isinstance(nested, dict):
        return _extract_speech(nested)
    if isinstance(nested, str) and nested.strip():
        return nested
    return None


def _interruption_prompt(text: str) -> str:
    return (
        "The user interrupted you while you were speaking. "
        f"They said: {text.strip()}\n"
        "Stop the previous spoken response and respond to this interruption directly."
    )
