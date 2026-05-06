"""STT smoke test: transcribe a wav file via the Parakeet wrapper.

Usage: python scripts/stt_smoke.py path/to/audio.wav
Audio is resampled to 16 kHz mono float32 before transcription.
"""

from __future__ import annotations

import asyncio
import sys

import numpy as np
import soundfile as sf

from voice.stt import ParakeetSTT


async def main(path: str) -> None:
    audio, sr = sf.read(path, dtype="float32", always_2d=False)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    if sr != ParakeetSTT.SAMPLE_RATE:
        # Lazy-import to avoid pulling soxr into runtime path.
        import soxr

        audio = soxr.resample(audio, sr, ParakeetSTT.SAMPLE_RATE).astype(np.float32)
    stt = ParakeetSTT()
    await stt.load()
    text = await stt.transcribe(audio)
    print("transcript:", repr(text))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python scripts/stt_smoke.py path/to/audio.wav", file=sys.stderr)
        raise SystemExit(2)
    asyncio.run(main(sys.argv[1]))
