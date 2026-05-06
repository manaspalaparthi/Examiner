from __future__ import annotations

import argparse
import asyncio
import json
import queue
import threading

import sounddevice as sd  # type: ignore[import-not-found]
import websockets


IN_RATE = 16_000
IN_BLOCK = 320  # 20 ms @ 16 kHz, int16 mono → 640 bytes per WS frame
OUT_RATE = 24_000
OUT_BLOCK = 480  # 20 ms @ 24 kHz


def _make_streams(in_q: queue.Queue, out_buf: bytearray, out_lock: threading.Lock):
    def in_cb(indata, frames, time_info, status):  # noqa: ARG001
        in_q.put(bytes(indata))

    def out_cb(outdata, frames, time_info, status):  # noqa: ARG001
        needed = len(outdata)
        with out_lock:
            available = min(needed, len(out_buf))
            outdata[:available] = bytes(out_buf[:available])
            del out_buf[:available]
            if available < needed:
                outdata[available:] = b"\x00" * (needed - available)

    in_stream = sd.RawInputStream(
        samplerate=IN_RATE,
        channels=1,
        dtype="int16",
        blocksize=IN_BLOCK,
        callback=in_cb,
    )
    out_stream = sd.RawOutputStream(
        samplerate=OUT_RATE,
        channels=1,
        dtype="int16",
        blocksize=OUT_BLOCK,
        callback=out_cb,
    )
    return in_stream, out_stream


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://localhost:8000/ws/voice")
    parser.add_argument("--agent", default="runtime")
    parser.add_argument("--config", default=None, help="src/agent YAML config path for --agent runtime")
    parser.add_argument("--greeting", default=None, help="optional startup greeting for --agent runtime")
    parser.add_argument("--initial-text", default=None, help="optional first text turn before listening")
    parser.add_argument("--user-id", default=None)
    parser.add_argument("--stt-model", default=None)
    parser.add_argument("--tts-voice", default=None)
    parser.add_argument("--tts-speed", type=float, default=None)
    parser.add_argument("--tts-lang", default=None)
    parser.add_argument("--vad-threshold", type=float, default=None)
    parser.add_argument("--echo-tail-s", type=float, default=None)
    parser.add_argument("--assistant-id", default="examiner")
    parser.add_argument("--topic", default=None)
    parser.add_argument("--details", default="")
    parser.add_argument("--difficulty", default="medium")
    parser.add_argument("--candidate", default=None)
    parser.add_argument("--num-questions", type=int, default=5)
    args = parser.parse_args()

    in_q: queue.Queue = queue.Queue()
    out_buf = bytearray()
    out_lock = threading.Lock()
    in_stream, out_stream = _make_streams(in_q, out_buf, out_lock)

    in_stream.start()
    out_stream.start()
    print(f"[tester] connecting to {args.url}")
    try:
        async with websockets.connect(args.url, max_size=None) as ws:
            agent_config = {}
            params = {}
            if args.agent == "langgraph":
                agent_config = {"assistant_id": args.assistant_id}
                params = {
                    "topic_name": args.topic or "General Knowledge",
                    "topic_details": args.details,
                    "difficulty": args.difficulty,
                    "candidate_name": args.candidate or "Candidate",
                    "num_questions": args.num_questions,
                    # Intentionally no `messages`: ExaminerStateMiddleware
                    # only injects the topic/candidate context when
                    # messages is empty (see src/examiner/state.py).
                }
            else:
                agent_config = {
                    key: value
                    for key, value in {
                        "config_path": args.config,
                        "greeting": args.greeting,
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
            voice_config = _voice_config_from_args(args)

            await ws.send(
                json.dumps(
                    {
                        "type": "start",
                        "agent": args.agent,
                        "agent_config": agent_config,
                        "params": params,
                        **({"voice_config": voice_config} if voice_config else {}),
                    }
                )
            )
            print("[tester] start frame sent; speak when you see [listening]")

            loop = asyncio.get_running_loop()

            async def send_audio() -> None:
                while True:
                    chunk = await loop.run_in_executor(None, in_q.get)
                    await ws.send(chunk)

            async def recv_loop() -> None:
                async for msg in ws:
                    if isinstance(msg, (bytes, bytearray)):
                        with out_lock:
                            out_buf.extend(msg)
                    else:
                        try:
                            data = json.loads(msg)
                        except json.JSONDecodeError:
                            print(f"[tester] non-json text frame: {msg[:80]}")
                            continue
                        kind = data.get("type", "?")
                        text = data.get("text", "")
                        if text:
                            print(f"[{kind}] {text}")
                        else:
                            print(f"[{kind}]")
                        if kind == "done":
                            return

            send_task = asyncio.create_task(send_audio())
            try:
                await recv_loop()
            finally:
                send_task.cancel()
    finally:
        in_stream.stop()
        out_stream.stop()
        in_stream.close()
        out_stream.close()


def _voice_config_from_args(args: argparse.Namespace) -> dict:
    config: dict = {}
    if args.stt_model is not None:
        config.setdefault("stt", {})["model_id"] = args.stt_model
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
        config["tts"] = tts
    if args.vad_threshold is not None:
        config.setdefault("vad", {})["threshold"] = args.vad_threshold
    if args.echo_tail_s is not None:
        config["echo_tail_s"] = args.echo_tail_s
    return config


if __name__ == "__main__":
    asyncio.run(main())
