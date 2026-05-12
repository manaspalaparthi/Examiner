from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence
from typing import Any

import numpy as np

from agent.config import LLMVoiceConfig, STTConfig, TTSConfig, VADConfig, VoiceConfig
from voice.stt import ParakeetSTT
from voice.tts import KokoroTTS


def build_livekit_stt(config: VoiceConfig) -> Any:
    """Build the STT component for a LiveKit AgentSession.

    `provider=local` keeps the current Parakeet model. Other providers are
    delegated to LiveKit Inference by model name, for example
    `deepgram/nova-3`.
    """
    if config.stt.provider == "local":
        return _build_local_parakeet_stt(config.stt)
    return _build_livekit_inference_stt(config.stt)


def build_livekit_tts(config: VoiceConfig) -> Any:
    """Build the TTS component for a LiveKit AgentSession."""
    if config.tts.provider == "local":
        return _build_local_kokoro_tts(config.tts)
    return _build_livekit_inference_tts(config.tts)


def build_livekit_llm(config: VoiceConfig) -> Any | None:
    """Build the optional LiveKit-managed LLM component.

    `provider=runtime` means the agent overrides `llm_node` and calls the
    project's existing AgentRuntime. Any other provider delegates to LiveKit
    Inference/plugin naming.
    """
    if config.llm.provider == "runtime":
        return None
    return _build_livekit_inference_llm(config.llm)


def build_livekit_vad(config: VoiceConfig) -> Any:
    """Build LiveKit VAD for turn detection and non-streaming local STT."""
    try:
        from livekit.plugins import silero
    except ImportError as e:  # pragma: no cover - only exercised with LiveKit deps installed
        raise RuntimeError(
            "LiveKit Silero VAD is required for the LiveKit voice pipeline. "
            "Install the voice-livekit extra."
        ) from e

    vad_cfg: VADConfig = config.vad
    return silero.VAD.load(
        min_speech_duration=0.05,
        min_silence_duration=vad_cfg.min_silence_ms / 1000,
        prefix_padding_duration=vad_cfg.speech_pad_ms / 1000,
        activation_threshold=vad_cfg.threshold,
        max_buffered_speech=vad_cfg.max_utterance_s,
    )


def build_livekit_turn_detection(config: VoiceConfig) -> Any | None:
    if config.turn_detection.provider != "livekit":
        return None
    if config.turn_detection.mode not in {"turn_detector", "multilingual"}:
        return None
    try:
        from livekit.plugins import turn_detector
    except ImportError as e:  # pragma: no cover - only exercised with LiveKit deps installed
        raise RuntimeError(
            "LiveKit turn detector is required for the configured voice pipeline. "
            "Install the voice-livekit extra."
        ) from e
    return turn_detector.MultilingualModel()


def _build_livekit_inference_stt(config: STTConfig) -> Any:
    try:
        from livekit.agents import inference
    except ImportError as e:  # pragma: no cover - only exercised with LiveKit deps installed
        raise RuntimeError("livekit-agents is required for LiveKit STT providers") from e
    kwargs = dict(config.options)
    if config.language:
        kwargs.setdefault("language", config.language)
    return inference.STT(model=config.model or config.model_id or "deepgram/nova-3", **kwargs)


def _build_livekit_inference_tts(config: TTSConfig) -> Any:
    try:
        from livekit.agents import inference
    except ImportError as e:  # pragma: no cover - only exercised with LiveKit deps installed
        raise RuntimeError("livekit-agents is required for LiveKit TTS providers") from e
    kwargs = dict(config.options)
    if config.voice:
        kwargs.setdefault("voice", config.voice)
    return inference.TTS(model=config.model or "cartesia/sonic-3", **kwargs)


def _build_livekit_inference_llm(config: LLMVoiceConfig) -> Any:
    try:
        from livekit.agents import inference
    except ImportError as e:  # pragma: no cover - only exercised with LiveKit deps installed
        raise RuntimeError("livekit-agents is required for LiveKit LLM providers") from e
    return inference.LLM(model=config.model or "openai/gpt-4o-mini", **dict(config.options))


def _build_local_parakeet_stt(config: STTConfig) -> Any:
    try:
        from livekit.agents import stt
    except ImportError as e:  # pragma: no cover - only exercised with LiveKit deps installed
        raise RuntimeError("livekit-agents is required for local STT adapters") from e

    class LocalParakeetSTT(stt.STT):
        def __init__(self) -> None:
            super().__init__(
                capabilities=stt.STTCapabilities(streaming=False, interim_results=False)
            )
            self._impl = ParakeetSTT(model_id=config.model_id or config.model)

        async def _recognize_impl(
            self,
            buffer: Any,
            *,
            language: str | None = None,
            conn_options: Any | None = None,  # noqa: ARG002
        ) -> Any:
            text = await self._impl.transcribe(_audio_buffer_to_float32(buffer))
            return stt.SpeechEvent(
                type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[
                    stt.SpeechData(
                        language=language or config.language or "en",
                        text=text,
                        start_time=0,
                        end_time=0,
                        confidence=1.0 if text else 0.0,
                    )
                ],
            )

    return LocalParakeetSTT()


def _build_local_kokoro_tts(config: TTSConfig) -> Any:
    try:
        from livekit.agents import tts
    except ImportError as e:  # pragma: no cover - only exercised with LiveKit deps installed
        raise RuntimeError("livekit-agents is required for local TTS adapters") from e

    class LocalKokoroTTS(tts.TTS):
        def __init__(self) -> None:
            super().__init__(
                capabilities=tts.TTSCapabilities(streaming=False),
                sample_rate=KokoroTTS.SAMPLE_RATE,
                num_channels=1,
            )
            self._impl = KokoroTTS(
                model_path=config.model_path,
                voices_path=config.voices_path,
                voice=config.voice,
                speed=config.speed,
                lang=config.lang,
            )

        def synthesize(
            self,
            text: str,
            *,
            conn_options: Any | None = None,
        ) -> Any:
            return LocalKokoroChunkedStream(tts=self, input_text=text, conn_options=conn_options)

        async def aclose(self) -> None:
            return None

    class LocalKokoroChunkedStream(tts.ChunkedStream):
        def __init__(
            self,
            *,
            tts: LocalKokoroTTS,
            input_text: str,
            conn_options: Any | None = None,
        ) -> None:
            super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)
            self._local_tts = tts

        async def _run(self, output_emitter: Any) -> None:
            request_id = uuid.uuid4().hex
            output_emitter.initialize(
                request_id=request_id,
                sample_rate=KokoroTTS.SAMPLE_RATE,
                num_channels=1,
                mime_type="audio/pcm",
            )
            async for frame in self._local_tts._impl.synth(
                self.input_text,
                voice=config.voice,
                speed=config.speed,
                lang=config.lang,
            ):
                output_emitter.push(frame)
                await asyncio.sleep(0)
            output_emitter.flush()

    return LocalKokoroTTS()


def _audio_buffer_to_float32(buffer: Any) -> np.ndarray:
    frames = _as_frame_sequence(buffer)
    chunks: list[np.ndarray] = []
    for frame in frames:
        samples = _frame_to_float32(frame)
        source_rate = int(getattr(frame, "sample_rate", ParakeetSTT.SAMPLE_RATE))
        if source_rate != ParakeetSTT.SAMPLE_RATE:
            samples = _resample(samples, source_rate, ParakeetSTT.SAMPLE_RATE)
        chunks.append(samples)
    if not chunks:
        return np.empty(0, dtype=np.float32)
    return np.concatenate(chunks).astype(np.float32, copy=False)


def _as_frame_sequence(buffer: Any) -> Sequence[Any]:
    if isinstance(buffer, (list, tuple)):
        return buffer
    if hasattr(buffer, "__iter__") and not hasattr(buffer, "data"):
        return list(buffer)
    return [buffer]


def _frame_to_float32(frame: Any) -> np.ndarray:
    data = getattr(frame, "data", frame)
    try:
        samples = np.asarray(data, dtype=np.int16)
    except (TypeError, ValueError):
        samples = np.frombuffer(data, dtype=np.int16)
    channels = int(getattr(frame, "num_channels", 1) or 1)
    if channels > 1 and samples.size >= channels:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return np.clip(samples.astype(np.float32) / 32768.0, -1.0, 1.0)


def _resample(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate or audio.size == 0:
        return audio
    target_len = max(1, int(round(audio.size * target_rate / source_rate)))
    x_old = np.linspace(0.0, 1.0, num=audio.size, endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=target_len, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)
