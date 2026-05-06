"""Latency harness for the voice stack.

Run from the repo root, for example:

    PYTHONPATH=src python -m tests.voice_latency tts --runs 5
    PYTHONPATH=src python -m tests.voice_latency stt samples/answer.wav --runs 3
    PYTHONPATH=src python -m tests.voice_latency ws --greeting "Ready." --audio samples/answer.wav

The file is intentionally not named ``test_*.py`` so normal pytest runs do not
load voice models or depend on a running WebSocket server.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import statistics
import sys
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    if args.command == "tts":
        result = asyncio.run(_bench_tts(args))
    elif args.command == "stt":
        result = asyncio.run(_bench_stt(args))
    elif args.command == "ws":
        result = asyncio.run(_bench_ws(args))
    else:
        parser.error(f"unknown command: {args.command}")
        return

    if getattr(args, "json", False):
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        _print_result(result)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure local STT/TTS latency or /ws/voice round-trip latency."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="emit machine-readable JSON",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    tts = sub.add_parser("tts", help="benchmark Kokoro TTS")
    tts.add_argument("--text", default="Hello, this is a short latency benchmark.")
    tts.add_argument("--runs", type=int, default=5)
    tts.add_argument("--warmups", type=int, default=1)
    tts.add_argument("--model-path", default=os.environ.get("KOKORO_MODEL", "kokoro-v1.0.onnx"))
    tts.add_argument("--voices-path", default=os.environ.get("KOKORO_VOICES", "voices-v1.0.bin"))
    tts.add_argument("--voice", default=os.environ.get("KOKORO_VOICE", "af_heart"))
    tts.add_argument("--speed", type=float, default=1.0)
    tts.add_argument("--lang", default="en-us")
    tts.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="emit machine-readable JSON",
    )

    stt = sub.add_parser("stt", help="benchmark Parakeet STT on a wav/flac/etc. file")
    stt.add_argument("audio", help="audio file to transcribe")
    stt.add_argument("--runs", type=int, default=3)
    stt.add_argument("--warmups", type=int, default=1)
    stt.add_argument("--model-id", default=None)
    stt.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="emit machine-readable JSON",
    )

    ws = sub.add_parser("ws", help="benchmark the FastAPI /ws/voice endpoint")
    ws.add_argument("--url", default="ws://127.0.0.1:8000/ws/voice")
    ws.add_argument("--agent", default="runtime")
    ws.add_argument("--config", default="config/agent.yaml", help="runtime agent config path")
    ws.add_argument("--greeting", default="Ready.", help="startup greeting; use '' to disable")
    ws.add_argument("--initial-text", default=None)
    ws.add_argument("--user-id", default="latency-test")
    ws.add_argument("--audio", default=None, help="optional user speech audio to stream after listening")
    ws.add_argument("--send-realtime", action="store_true", help="send audio at real-time pace")
    ws.add_argument("--post-silence-ms", type=int, default=900)
    ws.add_argument("--timeout-s", type=float, default=90.0)
    ws.add_argument("--stt-model", default=None)
    ws.add_argument("--tts-voice", default=None)
    ws.add_argument("--tts-speed", type=float, default=None)
    ws.add_argument("--tts-lang", default=None)
    ws.add_argument("--vad-threshold", type=float, default=None)
    ws.add_argument("--echo-tail-s", type=float, default=0.0)
    ws.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="emit machine-readable JSON",
    )
    return parser


async def _bench_tts(args: argparse.Namespace) -> dict[str, Any]:
    from voice.tts import KokoroTTS

    tts = KokoroTTS(
        model_path=args.model_path,
        voices_path=args.voices_path,
        voice=args.voice,
        speed=args.speed,
        lang=args.lang,
    )
    load_ms = await _elapsed_ms(tts.load())

    for _ in range(args.warmups):
        await _measure_tts_once(tts, args.text, args.voice, args.speed, args.lang)

    runs = [
        await _measure_tts_once(tts, args.text, args.voice, args.speed, args.lang)
        for _ in range(args.runs)
    ]
    return {
        "kind": "tts",
        "load_ms": load_ms,
        "text_chars": len(args.text),
        "runs": runs,
        "summary": _summaries(runs, ["first_frame_ms", "total_ms", "rtf"]),
    }


async def _measure_tts_once(tts: Any, text: str, voice: str, speed: float, lang: str) -> dict[str, Any]:
    start = time.perf_counter()
    first_frame_ms: float | None = None
    total_bytes = 0
    frames = 0
    async for frame in tts.synth(text, voice=voice, speed=speed, lang=lang):
        now = time.perf_counter()
        if first_frame_ms is None:
            first_frame_ms = (now - start) * 1000
        frames += 1
        total_bytes += len(frame)
    total_ms = (time.perf_counter() - start) * 1000
    audio_ms = total_bytes / 2 / tts.SAMPLE_RATE * 1000
    return {
        "first_frame_ms": first_frame_ms,
        "total_ms": total_ms,
        "audio_ms": audio_ms,
        "frames": frames,
        "rtf": total_ms / audio_ms if audio_ms else None,
    }


async def _bench_stt(args: argparse.Namespace) -> dict[str, Any]:
    from voice.stt import ParakeetSTT

    audio, source_sr = _read_audio(args.audio)
    audio = _resample_if_needed(audio, source_sr, ParakeetSTT.SAMPLE_RATE)
    audio_ms = len(audio) / ParakeetSTT.SAMPLE_RATE * 1000

    stt = ParakeetSTT(model_id=args.model_id)
    load_ms = await _elapsed_ms(stt.load())

    for _ in range(args.warmups):
        await stt.transcribe(audio)

    runs = []
    for _ in range(args.runs):
        start = time.perf_counter()
        transcript = await stt.transcribe(audio)
        total_ms = (time.perf_counter() - start) * 1000
        runs.append(
            {
                "total_ms": total_ms,
                "audio_ms": audio_ms,
                "rtf": total_ms / audio_ms if audio_ms else None,
                "transcript": transcript,
            }
        )

    return {
        "kind": "stt",
        "load_ms": load_ms,
        "audio_path": str(Path(args.audio).resolve()),
        "audio_ms": audio_ms,
        "runs": runs,
        "summary": _summaries(runs, ["total_ms", "rtf"]),
    }


async def _bench_ws(args: argparse.Namespace) -> dict[str, Any]:
    try:
        import websockets
    except ImportError as e:
        raise SystemExit("Install voice dependencies first: pip install -e '.[voice]'") from e

    start_frame = _ws_start_frame(args)
    audio: np.ndarray | None = None
    if args.audio:
        source_audio, source_sr = _read_audio(args.audio)
        audio = _resample_if_needed(source_audio, source_sr, 16_000)
        silence = np.zeros(int(16_000 * args.post_silence_ms / 1000), dtype=np.float32)
        audio = np.concatenate([audio, silence])

    markers: dict[str, float] = {}
    transcript: str | None = None
    events: list[dict[str, Any]] = []
    binary_frames = 0
    binary_bytes = 0

    async with websockets.connect(args.url, max_size=None) as ws:
        t0 = time.perf_counter()
        markers["connected"] = t0
        await ws.send(json.dumps(start_frame))
        markers["start_sent"] = time.perf_counter()
        audio_sent = False

        async def receive_until_done() -> None:
            nonlocal audio_sent, binary_frames, binary_bytes, transcript
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=args.timeout_s)
                now = time.perf_counter()
                if isinstance(msg, (bytes, bytearray)):
                    binary_frames += 1
                    binary_bytes += len(msg)
                    markers.setdefault("first_audio", now)
                    if "transcript" in markers:
                        markers.setdefault("first_response_audio", now)
                    continue

                event = json.loads(msg)
                events.append(event)
                kind = event.get("type")
                markers.setdefault(str(kind), now)
                if kind == "transcript":
                    transcript = event.get("text", "")
                if kind == "listening" and audio is not None and not audio_sent:
                    markers["user_audio_send_start"] = time.perf_counter()
                    await _send_pcm16_frames(ws.send, audio, realtime=args.send_realtime)
                    markers["user_audio_send_end"] = time.perf_counter()
                    audio_sent = True
                elif kind == "listening" and (audio is None or audio_sent):
                    if audio_sent:
                        markers.setdefault("response_listening", now)
                    return
                elif kind == "done":
                    return

        await receive_until_done()

    base = markers["start_sent"]
    metrics = {
        "connect_to_start_sent_ms": _delta(markers, "connected", "start_sent"),
        "start_to_speaking_started_ms": _delta_from(base, markers.get("speaking_started")),
        "start_to_first_audio_ms": _delta_from(base, markers.get("first_audio")),
        "start_to_first_listening_ms": _delta_from(base, markers.get("listening")),
        "binary_frames": binary_frames,
        "binary_audio_ms": binary_bytes / 2 / 24_000 * 1000,
    }
    if audio is not None:
        metrics.update(
            {
                "audio_duration_ms": len(audio) / 16_000 * 1000,
                "audio_send_ms": _delta(markers, "user_audio_send_start", "user_audio_send_end"),
                "audio_end_to_transcript_ms": _delta(markers, "user_audio_send_end", "transcript"),
                "transcript_to_response_audio_ms": _delta(markers, "transcript", "first_response_audio"),
                "transcript_to_listening_ms": _delta(markers, "transcript", "response_listening"),
            }
        )

    return {
        "kind": "ws",
        "url": args.url,
        "start_frame": start_frame,
        "metrics": metrics,
        "transcript": transcript,
        "events": events,
    }


def _ws_start_frame(args: argparse.Namespace) -> dict[str, Any]:
    agent_config: dict[str, Any] = {}
    params: dict[str, Any] = {}
    if args.agent == "runtime":
        agent_config = {
            key: value
            for key, value in {
                "config_path": args.config,
                "greeting": args.greeting or None,
            }.items()
            if value is not None
        }
        params = {
            key: value
            for key, value in {
                "initial_user_text": args.initial_text,
                "user_id": args.user_id,
            }.items()
            if value is not None
        }

    voice_config: dict[str, Any] = {}
    if args.stt_model is not None:
        voice_config.setdefault("stt", {})["model_id"] = args.stt_model
    tts = {
        key: value
        for key, value in {
            "voice": args.tts_voice,
            "speed": args.tts_speed,
            "lang": args.tts_lang,
        }.items()
        if value is not None
    }
    if tts:
        voice_config["tts"] = tts
    if args.vad_threshold is not None:
        voice_config.setdefault("vad", {})["threshold"] = args.vad_threshold
    if args.echo_tail_s is not None:
        voice_config["echo_tail_s"] = args.echo_tail_s

    frame = {
        "type": "start",
        "agent": args.agent,
        "agent_config": agent_config,
        "params": params,
    }
    if voice_config:
        frame["voice_config"] = voice_config
    return frame


async def _send_pcm16_frames(
    send: Callable[[bytes], Awaitable[None]],
    audio_f32: np.ndarray,
    *,
    realtime: bool,
) -> None:
    pcm16 = (np.clip(audio_f32, -1.0, 1.0) * 32767).astype(np.int16)
    frame_samples = 320
    for start in range(0, len(pcm16), frame_samples):
        await send(pcm16[start : start + frame_samples].tobytes())
        if realtime:
            await asyncio.sleep(0.02)


def _read_audio(path: str) -> tuple[np.ndarray, int]:
    try:
        import soundfile as sf
    except ImportError as e:
        raise SystemExit("Install voice dependencies first: pip install -e '.[voice]'") from e

    audio, sr = sf.read(path, dtype="float32", always_2d=False)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    return audio.astype(np.float32), int(sr)


def _resample_if_needed(audio: np.ndarray, source_sr: int, target_sr: int) -> np.ndarray:
    if source_sr == target_sr:
        return audio.astype(np.float32)
    try:
        import soxr

        return soxr.resample(audio, source_sr, target_sr).astype(np.float32)
    except ImportError:
        duration = len(audio) / source_sr
        source_x = np.linspace(0, duration, num=len(audio), endpoint=False)
        target_len = int(round(duration * target_sr))
        target_x = np.linspace(0, duration, num=target_len, endpoint=False)
        return np.interp(target_x, source_x, audio).astype(np.float32)


async def _elapsed_ms(awaitable: Awaitable[Any]) -> float:
    start = time.perf_counter()
    await awaitable
    return (time.perf_counter() - start) * 1000


def _summaries(runs: list[dict[str, Any]], keys: list[str]) -> dict[str, dict[str, float]]:
    summary = {}
    for key in keys:
        values = [run[key] for run in runs if isinstance(run.get(key), (int, float))]
        if values:
            summary[key] = _summary(values)
    return summary


def _summary(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    p95_index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return {
        "min": ordered[0],
        "median": statistics.median(ordered),
        "p95": ordered[p95_index],
        "max": ordered[-1],
    }


def _delta(markers: dict[str, float], start: str, end: str) -> float | None:
    if start not in markers or end not in markers:
        return None
    return (markers[end] - markers[start]) * 1000


def _delta_from(start: float, end: float | None) -> float | None:
    if end is None:
        return None
    return (end - start) * 1000


def _print_result(result: dict[str, Any]) -> None:
    kind = result["kind"]
    print(f"{kind.upper()} latency")
    if "load_ms" in result:
        print(f"load: {_ms(result['load_ms'])}")

    if kind in {"tts", "stt"}:
        print("\nsummary:")
        for metric, stats in result["summary"].items():
            suffix = "" if metric == "rtf" else " ms"
            print(
                f"  {metric}: min={stats['min']:.2f}{suffix}, "
                f"median={stats['median']:.2f}{suffix}, "
                f"p95={stats['p95']:.2f}{suffix}, max={stats['max']:.2f}{suffix}"
            )
        print("\nruns:")
        for idx, run in enumerate(result["runs"], start=1):
            bits = [f"run={idx}"]
            for key in ("first_frame_ms", "total_ms", "audio_ms", "rtf"):
                if key in run and run[key] is not None:
                    bits.append(f"{key}={run[key]:.2f}")
            if "transcript" in run:
                bits.append(f"transcript={run['transcript']!r}")
            print("  " + " ".join(bits))
        return

    if kind == "ws":
        print(f"url: {result['url']}")
        print("\nmetrics:")
        for key, value in result["metrics"].items():
            if value is None:
                print(f"  {key}: n/a")
            elif key.endswith("_ms"):
                print(f"  {key}: {_ms(value)}")
            else:
                print(f"  {key}: {value}")
        if result.get("transcript") is not None:
            print(f"\ntranscript: {result['transcript']!r}")


def _ms(value: float) -> str:
    return f"{value:.2f} ms"


if __name__ == "__main__":
    main()
