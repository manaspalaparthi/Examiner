"""Streams a single prompt through the configured provider; prints raw events.

Usage:
    PYTHONPATH=src python scripts/provider_smoke.py [--provider ollama|gemini] \
        [--model llama3.1] [--prompt "hello"]
"""
from __future__ import annotations

import argparse
import asyncio
import os

from dotenv import load_dotenv

load_dotenv()

from agent.providers.base import ProviderMessage
from agent.providers.factory import make_provider


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default=os.environ.get("MODEL_PROVIDER", "ollama"))
    parser.add_argument("--model", default=os.environ.get("MODEL_NAME", "llama3.1"))
    parser.add_argument("--prompt", default="In one sentence, what is supervised learning?")
    args = parser.parse_args()

    client = make_provider(args.provider)
    try:
        async for ev in client.stream(
            system="You are a terse assistant.",
            messages=[ProviderMessage(role="user", content=args.prompt)],
            tools=[],
            model=args.model,
            temperature=0.3,
        ):
            print(ev)
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
