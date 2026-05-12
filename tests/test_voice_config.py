from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np

from agent.config import load_agent_config
from voice.livekit_models import _audio_buffer_to_float32


def test_agent_config_includes_voice_pipeline() -> None:
    cfg = load_agent_config(Path("config/agent.yaml"))

    assert cfg.voice.transport == "livekit"
    assert cfg.voice.stt.provider == "local"
    assert cfg.voice.llm.provider == "runtime"
    assert cfg.voice.tts.provider == "local"
    assert cfg.voice.livekit.agent_name == "examiner-agent"


def test_livekit_audio_buffer_conversion_handles_mono_frames() -> None:
    pcm = (np.array([0, 16_384, -16_384], dtype=np.int16)).tobytes()
    frame = SimpleNamespace(data=pcm, sample_rate=16_000, num_channels=1)

    audio = _audio_buffer_to_float32(frame)

    assert np.allclose(audio, np.array([0.0, 0.5, -0.5], dtype=np.float32), atol=1e-4)
