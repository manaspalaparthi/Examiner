"""VAD smoke test: feed a wav into SileroVAD and print utterance lengths.

Usage: python scripts/vad_smoke.py path/to/audio.wav
"""

from __future__ import annotations

import sys

import numpy as np
import soundfile as sf

from voice.vad import SileroVAD


def main(path: str) -> None:
    audio, sr = sf.read(path, dtype="float32", always_2d=False)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    if sr != SileroVAD.SAMPLE_RATE:
        import soxr

        audio = soxr.resample(audio, sr, SileroVAD.SAMPLE_RATE).astype(np.float32)

    pcm16 = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
    vad = SileroVAD()

    # Drip-feed in 320-sample (20 ms) chunks the way the WebSocket would.
    step = 320 * 2  # bytes per frame
    utterances = []
    for i in range(0, len(pcm16), step):
        utterances.extend(vad.feed(pcm16[i : i + step]))

    print(f"input duration: {len(audio) / SileroVAD.SAMPLE_RATE:.2f}s")
    print(f"detected utterances: {len(utterances)}")
    for i, u in enumerate(utterances):
        print(f"  utt {i}: {len(u) / SileroVAD.SAMPLE_RATE:.2f}s")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python scripts/vad_smoke.py path/to/audio.wav", file=sys.stderr)
        raise SystemExit(2)
    main(sys.argv[1])
