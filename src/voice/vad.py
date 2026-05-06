from __future__ import annotations

import logging
from silero_vad import VADIterator, load_silero_vad

import numpy as np

log = logging.getLogger(__name__)


class SileroVAD:
    """Streaming VAD that emits one numpy buffer per detected utterance.

    Caller pushes raw int16 PCM bytes (16 kHz mono); `feed()` returns a list
    of completed utterances as float32 arrays in [-1, 1]. Internal buffering
    handles the 512-sample window Silero expects.

    `mute()` / `unmute()` are used by the session orchestrator to ignore
    audio when the floor is explicitly closed.
    """

    SAMPLE_RATE = 16_000
    WINDOW = 512  # samples — Silero's required window at 16 kHz

    def __init__(
        self,
        threshold: float = 0.5,
        min_silence_ms: int = 500,
        speech_pad_ms: int = 200,
        max_utterance_s: float = 30.0,
    ) -> None:
       

        self._model = load_silero_vad(onnx=True)
        self._iter = VADIterator(
            self._model,
            sampling_rate=self.SAMPLE_RATE,
            threshold=threshold,
            min_silence_duration_ms=min_silence_ms,
            speech_pad_ms=speech_pad_ms,
        )
        self._buffer = np.empty(0, dtype=np.float32)
        self._utterance: list[np.ndarray] = []
        self._in_speech = False
        self._max_samples = int(max_utterance_s * self.SAMPLE_RATE)
        self._muted = False

    def mute(self) -> None:
        self._muted = True
        self._reset()

    def unmute(self) -> None:
        self._reset()
        self._muted = False

    @property
    def in_speech(self) -> bool:
        return self._in_speech

    @property
    def speech_duration_ms(self) -> int:
        samples = sum(len(chunk) for chunk in self._utterance)
        return int(samples * 1000 / self.SAMPLE_RATE)

    @property
    def speech_rms(self) -> float:
        if not self._utterance:
            return 0.0
        samples = np.concatenate(self._utterance)
        return float(np.sqrt(np.mean(np.square(samples))))

    def _reset(self) -> None:
        self._iter.reset_states()
        self._buffer = np.empty(0, dtype=np.float32)
        self._utterance = []
        self._in_speech = False

    def feed(self, pcm_int16: bytes) -> list[np.ndarray]:
        if self._muted or not pcm_int16:
            return []
        samples = np.frombuffer(pcm_int16, dtype=np.int16).astype(np.float32) / 32768.0
        self._buffer = np.concatenate([self._buffer, samples])

        out: list[np.ndarray] = []
        while len(self._buffer) >= self.WINDOW:
            chunk = self._buffer[: self.WINDOW]
            self._buffer = self._buffer[self.WINDOW :]
            event = self._iter(chunk, return_seconds=False)

            if self._in_speech:
                self._utterance.append(chunk)

            if event:
                if "start" in event:
                    self._in_speech = True
                    self._utterance = [chunk]
                elif "end" in event and self._utterance:
                    out.append(np.concatenate(self._utterance))
                    self._utterance = []
                    self._in_speech = False

            # Safety: forcibly close runaway utterances.
            if (
                self._in_speech
                and sum(len(c) for c in self._utterance) >= self._max_samples
            ):
                log.warning("vad: utterance hit max_utterance_s, force-closing")
                out.append(np.concatenate(self._utterance))
                self._utterance = []
                self._in_speech = False
                self._iter.reset_states()
        return out
