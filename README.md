# Examiner — a basic LangChain DeepAgent

An oral-examiner agent built with [`deepagents`](https://github.com/langchain-ai/deepagents)
on top of LangGraph. Give it a topic, difficulty, and the candidate's name; it
plans 5 questions, asks them one at a time (pausing for each answer via a
LangGraph `interrupt`), evaluates each answer, and emits a final report.

The same graph runs in **LangGraph Studio** and as a **REST API** — both come
from a single `langgraph dev` command.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# edit .env — set MODEL_PROVIDER (google|ollama) and the matching key/url
```

### Provider options

- **Google Gemini**: set `MODEL_PROVIDER=google` and `GOOGLE_API_KEY=...`.
  Override the model with `MODEL_NAME` (default `gemini-2.0-flash`).
- **Ollama**: set `MODEL_PROVIDER=ollama`, run `ollama serve`, and
  `ollama pull llama3.1` (or whatever you set in `MODEL_NAME`).

## Run in LangGraph Studio

```bash
langgraph dev
```

This serves the graph at `http://localhost:2024` and opens Studio in your
browser. Start a new run with input like:

```json
{
  "topic_name": "Binary Search",
  "topic_details": "Algorithm fundamentals, complexity, edge cases like empty arrays and duplicates",
  "difficulty": "medium",
  "candidate_name": "Manas",
  "messages": [{"role": "user", "content": "Begin the exam."}]
}
```

The graph will pause at each `ask_candidate` call. Studio shows an interrupt
panel — type the candidate's answer there to resume.

## Run via REST API (streaming)

`langgraph dev` exposes the standard LangGraph Server API on the same port.
The examples below hit `/runs/stream`, so LLM tokens arrive incrementally as
Server-Sent Events. `stream_mode: ["messages", "updates"]` multiplexes per-token
LLM chunks (`event: messages`) with node-level state diffs — including the
`__interrupt__` payload that surfaces each question (`event: updates`).

> Use `curl -N` to disable output buffering; without it the terminal will make
> the stream look like one batched response.

**1. Create a thread and start a streaming run:**

```bash
THREAD=$(curl -s -X POST http://localhost:2024/threads \
  -H 'Content-Type: application/json' -d '{}' | jq -r .thread_id)

curl -N -X POST http://localhost:2024/threads/$THREAD/runs/stream \
  -H 'Content-Type: application/json' -d '{
    "assistant_id": "examiner",
    "stream_mode": ["messages", "updates"],
    "input": {
      "topic_name": "Binary Search",
      "topic_details": "Algorithm fundamentals, complexity, edge cases",
      "difficulty": "medium",
      "candidate_name": "Manas",
      "messages": [{"role": "user", "content": "Begin the exam."}]
    }
  }'
```

You'll see frames like:

```
event: messages
data: [{"content": "Let", "type": "AIMessageChunk", ...}, {...metadata...}]

event: messages
data: [{"content": "'s", "type": "AIMessageChunk", ...}, {...}]
...
event: updates
data: {"__interrupt__": [{"value": {"type": "question", "question": "..."}}]}
```

The stream closes when the graph hits the `ask_candidate` interrupt.

**2. Resume with the candidate's answer (also streaming):**

```bash
curl -N -X POST http://localhost:2024/threads/$THREAD/runs/stream \
  -H 'Content-Type: application/json' -d '{
    "assistant_id": "examiner",
    "stream_mode": ["messages", "updates"],
    "command": { "resume": "Binary search has O(log n) time complexity." }
  }'
```

Repeat until the stream closes without an `__interrupt__` updates frame — the
final `messages` chunks make up the report, and `qa_history` in state holds the
structured results.

### Python client (langgraph_sdk)

Parsing SSE by hand is tedious; the Python SDK gives you typed chunks:

```python
import asyncio
from langgraph_sdk import get_client


async def main():
    client = get_client(url="http://localhost:2024")
    thread = await client.threads.create()

    async for chunk in client.runs.stream(
        thread["thread_id"],
        assistant_id="examiner",
        input={
            "topic_name": "Binary Search",
            "topic_details": "Algorithm fundamentals, complexity, edge cases",
            "difficulty": "medium",
            "candidate_name": "Manas",
            "messages": [{"role": "user", "content": "Begin the exam."}],
        },
        stream_mode=["messages", "updates"],
    ):
        if chunk.event == "messages":
            token = chunk.data[0].get("content", "")
            if token:
                print(token, end="", flush=True)
        elif chunk.event == "updates" and "__interrupt__" in chunk.data:
            print("\n[interrupt]", chunk.data["__interrupt__"][0]["value"])


asyncio.run(main())
```

Resume the same way, swapping `input=...` for `command={"resume": "..."}`.



## Voice POC

A FastAPI WebSocket front-door that wraps the agent in a generic voice
pipeline: **Silero VAD → Parakeet TDT STT → AgentBackend → sentence buffer
→ Kokoro TTS**. Nothing in the pipeline depends on LangChain — `AgentBackend`
is an ABC with three event types (`TokenEvent`, `TurnEndEvent`, `DoneEvent`).
The default backend is now `runtime`, which wraps `src/agent`. The older
LangGraph/Examiner backend remains registered as `langgraph`.

### Install

```bash
pip install -e ".[voice,agent,voice-tester]"
```

Download Kokoro model files into the working directory (or set
`KOKORO_MODEL` / `KOKORO_VOICES`):

```bash
.venv/bin/python scripts/download_kokoro.py
```

Silero-VAD ships with its model bundled. Parakeet (parakeet-mlx on Apple
Silicon, NeMo elsewhere) downloads on first transcription. STT/TTS models load
lazily when the first voice WebSocket starts; set `VOICE_PRELOAD_MODELS=1` if
you want startup to warm the defaults.

### Run end-to-end

```bash
# T1 — database for src/agent
docker compose up -d postgres
PYTHONPATH=src python -m agent.db.migrations

# T2 — voice service
.venv/bin/uvicorn voice.app:app --port 8000

# T3 — mic-in / speaker-out tester
.venv/bin/python -m voice.tester
```

To use the old Examiner LangGraph graph instead, run `langgraph dev` and pass
`--agent langgraph --assistant-id examiner` to the tester, along with the
Examiner topic/candidate flags.

### Wire protocol (`/ws/voice`)

Client → server:
- First text frame: `{"type":"start","agent":"runtime","agent_config":{"config_path":"config/agent.yaml"},"params":{...},"voice_config":{...}}`. `params` is opaque and forwarded to the agent backend's `start()`.
- Then binary frames: int16 PCM, 16 kHz mono, 20 ms each (640 bytes).

Server → client:
- Binary: int16 PCM, 24 kHz mono (Kokoro native), ~40 ms per frame.
- Text JSON control: `transcript`, `agent_text` (one per sentence — useful for captions), `speaking_started`/`speaking_ended`, `listening`, `done`.

### Frontend configuration API

The FastAPI app also exposes REST endpoints intended for a Next.js settings UI:

- `GET /api/voice/capabilities` — registered agent backends, audio formats, and JSON schemas for voice/session config.
- `GET /api/voice/config` — current default voice config derived from environment.
- `POST /api/voice/config/validate` — validate and normalize a `voice_config` payload.
- `POST /api/voice/start/validate` — validate the first WebSocket `start` frame before opening audio.
- `GET /api/agents/runtime/config?path=config/agent.yaml` — read a `src/agent` YAML config.
- `POST /api/agents/runtime/config/validate` — validate and normalize a runtime agent config.
- `PUT /api/agents/runtime/config` — save a runtime agent config under `config/`.

CORS defaults allow `http://localhost:3000` and `http://127.0.0.1:3000`.
Override with `VOICE_CORS_ORIGINS` as a comma-separated list.

Example WebSocket start frame with per-session voice settings:

```json
{
  "type": "start",
  "agent": "runtime",
  "agent_config": {
    "config_path": "config/agent.yaml",
    "greeting": "Hi, I'm ready."
  },
  "params": {
    "user_id": "web-user-123"
  },
  "voice_config": {
    "tts": {
      "voice": "af_heart",
      "speed": 1.0,
      "lang": "en-us"
    },
    "vad": {
      "threshold": 0.5,
      "min_silence_ms": 500,
      "speech_pad_ms": 200,
      "max_utterance_s": 30
    },
    "echo_tail_s": 0.7
  }
}
```

### Project layout

```
Examiner/
├── langgraph.json
├── pyproject.toml
├── src/examiner/               # the LangGraph agent (unchanged)
├── src/voice/
│   ├── agent_base.py           # AgentBackend ABC + event types
│   ├── agent_langgraph.py      # LangGraphAgent implementation
│   ├── agent_runtime.py        # src/agent runtime implementation
│   ├── agent_registry.py       # name → backend class registry
│   ├── vad.py                  # SileroVAD (ONNX)
│   ├── stt.py                  # Parakeet TDT (parakeet-mlx | NeMo)
│   ├── tts.py                  # Kokoro (kokoro-onnx)
│   ├── sentencizer.py          # token stream → sentence stream
│   ├── session.py              # VoiceSession orchestrator
│   ├── app.py                  # FastAPI app + /ws/voice
│   └── tester.py               # CLI mic/speaker harness
├── scripts/
│   ├── download_kokoro.py      # fetches kokoro-v1.0.onnx + voices-v1.0.bin
│   ├── vad_smoke.py            # python scripts/vad_smoke.py audio.wav
│   ├── stt_smoke.py            # python scripts/stt_smoke.py audio.wav
│   └── tts_smoke.py            # writes out.wav
└── tests/test_sentencizer.py
```
