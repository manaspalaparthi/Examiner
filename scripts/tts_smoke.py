"""End-to-end TTS smoke test: synth a sentence to out.wav."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import numpy as np
import soundfile as sf

from voice.tts import KokoroTTS


async def main() -> None:
    tts = KokoroTTS(
        model_path=os.environ.get("KOKORO_MODEL", "kokoro-v1.0.onnx"),
        voices_path=os.environ.get("KOKORO_VOICES", "voices-v1.0.bin"),
        voice=os.environ.get("KOKORO_VOICE", "af_heart"),
    )
    await tts.load()
    text = "Hello, this is a smoke test for Kokoro text to speech."
    chunks: list[bytes] = []
    async for frame in tts.synth(text):
        chunks.append(frame)
    pcm = np.frombuffer(b"".join(chunks), dtype=np.int16)
    out = Path("out.wav")
    sf.write(out, pcm, KokoroTTS.SAMPLE_RATE, subtype="PCM_16")
    print(f"wrote {out} ({len(pcm) / KokoroTTS.SAMPLE_RATE:.2f}s, {len(chunks)} frames)")


if __name__ == "__main__":
    asyncio.run(main())
