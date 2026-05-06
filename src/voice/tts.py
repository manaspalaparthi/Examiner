from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator

import numpy as np

log = logging.getLogger(__name__)


class KokoroTTS:
    """Sentence-in, PCM-frames-out wrapper around kokoro-onnx.

    Kokoro returns the full waveform per `create()` call; we slice it into
    fixed-size frames before yielding so the WebSocket sends are steady and
    the client can begin playback before we've even started synthesizing
    the next sentence.
    """

    SAMPLE_RATE = 24_000
    FRAME_MS = 40
    FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000

    def __init__(
        self,
        model_path: str,
        voices_path: str,
        voice: str = "af_heart",
        speed: float = 1.0,
        lang: str = "en-us",
    ) -> None:
        self._model_path = model_path
        self._voices_path = voices_path
        self._voice = voice
        self._speed = speed
        self._lang = lang
        self._impl = None
        self._lock = asyncio.Lock()
        self._loaded = asyncio.Event()

    @property
    def loaded(self) -> bool:
        return self._loaded.is_set()

    async def load(self) -> None:
        if self._loaded.is_set():
            return
        for path in (self._model_path, self._voices_path):
            if not os.path.exists(path):
                raise FileNotFoundError(
                    f"Kokoro model file not found: {path}. "
                    "Download kokoro-v1.0.onnx and voices-v1.0.bin from "
                    "https://github.com/thewh1teagle/kokoro-onnx/releases"
                )
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._load_sync)
        self._loaded.set()

    def _load_sync(self) -> None:
        from kokoro_onnx import Kokoro  # type: ignore[import-not-found]

        log.info("tts: loading Kokoro from %s", self._model_path)
        self._impl = Kokoro(self._model_path, self._voices_path)

    async def synth(
        self,
        text: str,
        *,
        voice: str | None = None,
        speed: float | None = None,
        lang: str | None = None,
    ) -> AsyncIterator[bytes]:
        if not self._loaded.is_set():
            await self.load()
        if not text.strip():
            return
        async with self._lock:
            loop = asyncio.get_running_loop()
            samples, sr = await loop.run_in_executor(
                None,
                self._synth_sync,
                text,
                voice or self._voice,
                self._speed if speed is None else speed,
                lang or self._lang,
            )
        if sr != self.SAMPLE_RATE:
            log.warning("tts: unexpected sample rate %d (expected %d)", sr, self.SAMPLE_RATE)
        pcm16 = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
        for i in range(0, len(pcm16), self.FRAME_SAMPLES):
            chunk = pcm16[i : i + self.FRAME_SAMPLES]
            yield chunk.tobytes()

    def _synth_sync(self, text: str, voice: str, speed: float, lang: str):
        return self._impl.create(  # type: ignore[union-attr]
            text,
            voice=voice,
            speed=speed,
            lang=lang,
        )
