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

## Run via REST API

`langgraph dev` exposes the standard LangGraph Server API on the same port.

**1. Create a thread and start a run:**

```bash
THREAD=$(curl -s -X POST http://localhost:2024/threads \
  -H 'Content-Type: application/json' -d '{}' | jq -r .thread_id)

curl -s -X POST http://localhost:2024/threads/$THREAD/runs/wait \
  -H 'Content-Type: application/json' -d '{
    "assistant_id": "examiner",
    "input": {
      "topic_name": "Binary Search",
      "topic_details": "Algorithm fundamentals, complexity, edge cases",
      "difficulty": "medium",
      "candidate_name": "Manas",
      "messages": [{"role": "user", "content": "Begin the exam."}]
    }
  }'
```

The response will include an `__interrupt__` entry containing the question.

**2. Resume with the candidate's answer:**

```bash
curl -s -X POST http://localhost:2024/threads/$THREAD/runs/wait \
  -H 'Content-Type: application/json' -d '{
    "assistant_id": "examiner",
    "command": { "resume": "Binary search has O(log n) time complexity." }
  }'
```

Repeat until the run finishes without an interrupt — the final assistant
message is the report, and `qa_history` in state holds the structured results.

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
