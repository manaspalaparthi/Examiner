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

## Project layout

```
Examiner/
├── langgraph.json              # registers the graph for Studio + API
├── pyproject.toml
├── .env.example
└── src/examiner/
    ├── agent.py                # builds and exports `agent`
    ├── model.py                # google | ollama factory
    ├── state.py                # ExaminerState (extends DeepAgentState)
    ├── tools.py                # ask_candidate + record_evaluation
    └── prompts.py              # examiner system instructions
```
