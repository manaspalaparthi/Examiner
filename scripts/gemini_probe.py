"""Dump the raw streaming structure from Google's Gemini API for a given model.

For each chunk we print:
  - finish_reason / safety ratings
  - content.role
  - for each part: every public attribute, with its value (text, thought,
    function_call, function_response, inline_data, etc.)

This lets us see definitively whether the model surfaces a structured
`thought` channel, a typed reasoning block, or just plain text.

Usage:
    PYTHONPATH=src python scripts/gemini_probe.py \
        [--model gemma-4-31b-it] \
        [--prompt "hi"] \
        [--thinking on|off|auto]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import textwrap

from dotenv import load_dotenv

load_dotenv()

from google import genai
from google.genai import types


PUBLIC_PART_ATTRS = (
    "text", "thought", "function_call", "function_response",
    "inline_data", "file_data", "executable_code", "code_execution_result",
)


def fmt(value):
    s = repr(value)
    if len(s) > 200:
        s = s[:200] + "…"
    return s


async def run(model_name: str, prompt: str, thinking: str) -> None:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise SystemExit("GOOGLE_API_KEY not set")
    client = genai.Client(api_key=api_key)

    config_kwargs = {
        "temperature": 0.3,
        "system_instruction": "You are a helpful assistant.",
    }
    if thinking != "auto":
        config_kwargs["thinking_config"] = types.ThinkingConfig(
            include_thoughts=thinking == "on",
        )

    print(f"=== model={model_name} prompt={prompt!r} thinking={thinking} ===")
    response = await client.aio.models.generate_content_stream(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(**config_kwargs),
    )

    chunk_idx = 0
    async for chunk in response:
        chunk_idx += 1
        print(f"\n--- chunk #{chunk_idx} ---")
        print(f"chunk type: {type(chunk).__name__}")
        cands = getattr(chunk, "candidates", None) or []
        for ci, cand in enumerate(cands):
            print(f"  candidate[{ci}]:")
            print(f"    finish_reason: {getattr(cand, 'finish_reason', None)!r}")
            print(f"    safety_ratings: {fmt(getattr(cand, 'safety_ratings', None))}")
            content = getattr(cand, "content", None)
            if content is None:
                print("    content: None")
                continue
            print(f"    content.role: {getattr(content, 'role', None)!r}")
            parts = getattr(content, "parts", None) or []
            for pi, part in enumerate(parts):
                print(f"    part[{pi}] type={type(part).__name__}")
                # All public attributes on the proto
                for attr in PUBLIC_PART_ATTRS:
                    if hasattr(part, attr):
                        v = getattr(part, attr)
                        # protos: text falsy when not set, function_call has .name
                        if attr == "text":
                            shown = textwrap.shorten(repr(v), width=160) if v else "''"
                            print(f"      .{attr}: {shown}")
                        elif attr == "thought":
                            print(f"      .{attr}: {v!r}  <-- thinking flag")
                        elif attr == "function_call":
                            name = getattr(v, "name", "") if v else ""
                            args = dict(getattr(v, "args", {}) or {})
                            print(f"      .{attr}: name={name!r} args={fmt(args)}")
                        else:
                            present = bool(v)
                            if present:
                                print(f"      .{attr}: {fmt(v)}")
                # Catch any other interesting attrs we didn't pre-list
                other = [
                    a for a in dir(part)
                    if not a.startswith("_")
                    and a not in PUBLIC_PART_ATTRS
                    and not callable(getattr(part, a, None))
                ]
                if other:
                    print(f"      other attrs: {other}")
        # Top-level prompt_feedback etc.
        pf = getattr(chunk, "prompt_feedback", None)
        if pf:
            print(f"  prompt_feedback: {fmt(pf)}")
        usage = getattr(chunk, "usage_metadata", None)
        if usage:
            print(f"  usage_metadata: {fmt(usage)}")

    print("\n=== done ===")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=os.environ.get("MODEL_NAME", "gemini-2.0-flash"))
    parser.add_argument("--prompt", default="hi this is manas")
    parser.add_argument("--thinking", choices=["on", "off", "auto"], default="auto")
    args = parser.parse_args()
    asyncio.run(run(args.model, args.prompt, args.thinking))


if __name__ == "__main__":
    main()
