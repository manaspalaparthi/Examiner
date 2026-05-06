"""Interactive REPL for the lightweight agent runtime.

Usage:
    PYTHONPATH=src python scripts/agent_chat.py [--config config/agent.yaml]

Each line you type starts a new turn on the same conversation. The runtime
streams `AckEvent`, then `TextDelta`s, then `ToolStart/End` events if any
tools fire, and ends with `DoneEvent`. Press Ctrl-D / Ctrl-C to quit.

Requires:
  - DATABASE_URL env (or .env via your shell), pointing at the docker-compose
    Postgres started with `docker compose up -d postgres`.
  - Migrations applied:  PYTHONPATH=src python -m agent.db.migrations
  - The configured provider reachable (Ollama running, or GOOGLE_API_KEY set).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from dotenv import load_dotenv

load_dotenv()

from agent.config import load_agent_config
from agent.db.pool import create_pool
from agent.events import (
    AckEvent,
    DoneEvent,
    ErrorEvent,
    TextDelta,
    ToolEnd,
    ToolStart,
)
from agent.mcp.registry import MCPRegistry
from agent.providers.factory import make_provider
from agent.runtime import AgentRuntime
from agent.tools.base import ToolRegistry


async def repl(config_path: str | None) -> None:
    cfg = load_agent_config(config_path)
    pool = await create_pool()
    tools = ToolRegistry()
    mcp = MCPRegistry(tools)
    await mcp.start(cfg.mcp_servers)
    llm = make_provider(cfg.provider)
    runtime = AgentRuntime(cfg=cfg, pool=pool, llm=llm, tools=tools)
    print(f"agent={cfg.agent_id} provider={cfg.provider} model={cfg.model}")
    print("type a message and press enter; Ctrl-D to quit.\n")

    conv_id = None
    loop = asyncio.get_running_loop()
    try:
        while True:
            try:
                line = await loop.run_in_executor(None, _readline, "you> ")
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if not line:
                continue
            print("agent> ", end="", flush=True)
            async for ev in runtime.run_turn(user_text=line, conversation_id=conv_id):
                if isinstance(ev, AckEvent):
                    print(f"[ack] {ev.text}")
                    print("agent> ", end="", flush=True)
                elif isinstance(ev, TextDelta):
                    print(ev.text, end="", flush=True)
                elif isinstance(ev, ToolStart):
                    print(f"\n[tool→ {ev.tool_name} args={ev.args}]")
                    print("agent> ", end="", flush=True)
                elif isinstance(ev, ToolEnd):
                    status = "ok" if ev.ok else f"err: {ev.error}"
                    print(f"\n[tool← {ev.tool_name} {ev.latency_ms}ms {status}]")
                    print("agent> ", end="", flush=True)
                elif isinstance(ev, ErrorEvent):
                    print(f"\n[error:{ev.kind}] {ev.message}")
                elif isinstance(ev, DoneEvent):
                    print(f"\n[done {ev.total_ms}ms]\n")
                    conv_id = ev.conversation_id
    finally:
        await mcp.aclose()
        await llm.aclose()
        await pool.close()


def _readline(prompt: str) -> str:
    sys.stdout.write(prompt)
    sys.stdout.flush()
    line = sys.stdin.readline()
    if not line:
        raise EOFError
    return line.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(repl(args.config))


if __name__ == "__main__":
    main()
