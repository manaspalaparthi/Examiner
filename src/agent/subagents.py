from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from .errors import ToolError, ToolValidationError
from .providers.base import (
    LLMClient,
    LLMError,
    LLMFinish,
    LLMTextDelta,
    LLMThinkingDelta,
    LLMToolCall,
    ProviderMessage,
    ProviderToolCall,
    ToolSchema,
)
from .tools.base import ToolContext, ToolResult, ToolSpec, validate_args
from .tools.schema import strip_titles_and_defaults

DELEGATE_TOOL_NAME = "delegate_to_subagents"

_TASK_CONTEXT_CAP = 10_000
_WORKER_OUTPUT_CAP = 8_000


class SubagentTask(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    instructions: str = Field(..., min_length=1, max_length=4_000)
    kind: Literal["general", "analysis", "research", "websearch", "coding"] = "general"


class DelegateSubagentsArgs(BaseModel):
    tasks: list[SubagentTask] = Field(..., min_length=1, max_length=4)
    synthesis_instructions: str | None = Field(default=None, max_length=1_000)


@dataclass(slots=True)
class SubagentSettings:
    max_children: int = 4
    max_iters: int = 4
    timeout_s: float = 45.0
    tool_timeout_s: float = 10.0


def make_delegation_tool(
    *,
    llm: LLMClient,
    system_prompt: str,
    parent_messages: list[ProviderMessage],
    worker_tools: list[ToolSpec],
    model: str,
    temperature: float,
    max_tokens: int | None,
    thinking_enabled: bool,
    settings: SubagentSettings,
) -> ToolSpec:
    """Create the built-in delegation tool for the current runtime turn."""

    usable_tools = [t for t in worker_tools if t.name != DELEGATE_TOOL_NAME]
    schemas = [t.to_provider_schema() for t in usable_tools]
    tool_map = {t.name: t for t in usable_tools}
    max_children = min(settings.max_children, 4)
    semaphore = asyncio.Semaphore(max_children)

    async def handler(args: DelegateSubagentsArgs, ctx: ToolContext) -> ToolResult:
        if len(args.tasks) > max_children:
            return ToolResult(
                output=(
                    f"Requested {len(args.tasks)} subagents, but this agent is capped at "
                    f"{max_children}. Retry with at most {max_children} focused tasks."
                ),
                summary="too many subagent tasks requested",
                metadata={"ok": False, "requested": len(args.tasks), "max_children": max_children},
            )

        context = _format_parent_context(parent_messages)

        async def run_one(index: int, task: SubagentTask) -> _SubagentResult:
            async with semaphore:
                return await _run_worker(
                    index=index,
                    task=task,
                    ctx=ctx,
                    llm=llm,
                    system_prompt=system_prompt,
                    parent_context=context,
                    tool_map=tool_map,
                    tool_schemas=schemas,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    thinking_enabled=thinking_enabled,
                    settings=settings,
                )

        started = time.monotonic()
        results = await asyncio.gather(
            *(run_one(i, task) for i, task in enumerate(args.tasks, start=1))
        )
        output = _format_results(results, synthesis_instructions=args.synthesis_instructions)
        failures = sum(1 for result in results if not result.ok)
        return ToolResult(
            output=output,
            summary=f"ran {len(results)} subagent(s), {failures} failed",
            metadata={
                "ok": failures == 0,
                "subagents": len(results),
                "failures": failures,
                "latency_ms": int((time.monotonic() - started) * 1000),
            },
        )

    return ToolSpec(
        name=DELEGATE_TOOL_NAME,
        description=(
            "Run up to 4 focused subagents in parallel for web search, research, "
            "coding investigation, or complicated analysis. Use only when the "
            "request benefits from splitting into independent tasks. Each "
            "subagent can use the non-delegation tools available to the parent, "
            "including any configured web-search MCP tools."
        ),
        handler=handler,
        parameters=strip_titles_and_defaults(DelegateSubagentsArgs.model_json_schema()),
        groups=("subagents",),
        validator=DelegateSubagentsArgs,
        timeout_s=settings.timeout_s,
    )


@dataclass(slots=True)
class _SubagentResult:
    index: int
    title: str
    kind: str
    ok: bool
    output: str
    latency_ms: int
    tool_summaries: list[str]
    error: str | None = None


async def _run_worker(
    *,
    index: int,
    task: SubagentTask,
    ctx: ToolContext,
    llm: LLMClient,
    system_prompt: str,
    parent_context: str,
    tool_map: dict[str, ToolSpec],
    tool_schemas: list[ToolSchema],
    model: str,
    temperature: float,
    max_tokens: int | None,
    thinking_enabled: bool,
    settings: SubagentSettings,
) -> _SubagentResult:
    started = time.monotonic()
    messages = [
        ProviderMessage(
            role="user",
            content=_worker_prompt(task, parent_context=parent_context),
        )
    ]
    tool_summaries: list[str] = []

    for _ in range(settings.max_iters):
        text_buf: list[str] = []
        pending_calls: list[LLMToolCall] = []
        stream = llm.stream(
            system=_worker_system_prompt(system_prompt),
            messages=messages,
            tools=tool_schemas,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            thinking_enabled=thinking_enabled,
        )
        async for event in stream:
            if isinstance(event, LLMTextDelta):
                text_buf.append(event.text)
            elif isinstance(event, LLMThinkingDelta):
                continue
            elif isinstance(event, LLMToolCall):
                pending_calls.append(event)
            elif isinstance(event, LLMError):
                return _result(
                    index=index,
                    task=task,
                    started=started,
                    ok=False,
                    output="",
                    tool_summaries=tool_summaries,
                    error=event.message,
                )
            elif isinstance(event, LLMFinish):
                continue

        assistant_text = "".join(text_buf)
        if not pending_calls:
            return _result(
                index=index,
                task=task,
                started=started,
                ok=True,
                output=assistant_text.strip() or "(no findings returned)",
                tool_summaries=tool_summaries,
            )

        messages.append(
            ProviderMessage(
                role="assistant",
                content=assistant_text or None,
                tool_calls=[
                    ProviderToolCall(call_id=call.call_id, name=call.name, args=call.args)
                    for call in pending_calls
                ],
            )
        )
        for call in pending_calls:
            tool_output, summary = await _dispatch_worker_tool(
                call=call,
                parent_ctx=ctx,
                tool_map=tool_map,
                default_timeout_s=settings.tool_timeout_s,
            )
            tool_summaries.append(summary)
            messages.append(
                ProviderMessage(
                    role="tool",
                    content=tool_output,
                    tool_call_id=call.call_id,
                )
            )

    return _result(
        index=index,
        task=task,
        started=started,
        ok=False,
        output="",
        tool_summaries=tool_summaries,
        error=f"subagent exceeded {settings.max_iters} tool iterations",
    )


async def _dispatch_worker_tool(
    *,
    call: LLMToolCall,
    parent_ctx: ToolContext,
    tool_map: dict[str, ToolSpec],
    default_timeout_s: float,
) -> tuple[str, str]:
    spec = tool_map.get(call.name)
    if spec is None:
        err = f"unknown tool: {call.name}"
        return err, err
    try:
        args = validate_args(spec, call.args)
    except ToolValidationError as e:
        err = f"invalid {call.name} args: {e}"
        return err, err

    ctx = ToolContext(
        conversation_id=parent_ctx.conversation_id,
        call_id=call.call_id,
        metadata={**parent_ctx.metadata, "subagent": True},
    )
    timeout_s = spec.timeout_s or default_timeout_s
    try:
        result = await asyncio.wait_for(spec.handler(args, ctx), timeout=timeout_s)
    except asyncio.TimeoutError:
        err = f"tool {call.name} timed out after {timeout_s}s"
        return err, err
    except ToolError as e:
        err = f"tool {call.name} error: {e}"
        return err, err
    except Exception as e:  # noqa: BLE001 - tool failures are data for the worker.
        err = f"tool {call.name} error: {type(e).__name__}: {e}"
        return err, err

    output = _truncate(result.output, _WORKER_OUTPUT_CAP)
    summary = f"{call.name}: {result.summary or _short(output)}"
    return output, summary


def _worker_system_prompt(parent_system: str) -> str:
    return (
        "You are a focused subagent working for a parent assistant. "
        "Complete only the assigned task. Be concise, cite URLs or tool-provided "
        "sources when available, and clearly separate verified facts from "
        "inferences. Do not ask the user follow-up questions.\n\n"
        f"Parent assistant instructions:\n{parent_system.strip()}"
    )


def _worker_prompt(task: SubagentTask, *, parent_context: str) -> str:
    return (
        f"Task kind: {task.kind}\n"
        f"Task title: {task.title}\n\n"
        f"Instructions:\n{task.instructions.strip()}\n\n"
        f"Recent parent conversation context:\n{parent_context or '(none)'}\n\n"
        "Return only the findings needed by the parent assistant."
    )


def _format_parent_context(messages: list[ProviderMessage]) -> str:
    parts: list[str] = []
    for message in messages[-12:]:
        if message.role == "tool":
            label = f"tool:{message.tool_call_id or 'result'}"
        else:
            label = message.role
        content = message.content or ""
        if message.tool_calls:
            calls = [
                {"name": call.name, "args": call.args}
                for call in message.tool_calls
                if call.name != DELEGATE_TOOL_NAME
            ]
            if calls:
                content = f"{content}\nTool calls: {json.dumps(calls, default=str)}"
        if content.strip():
            parts.append(f"{label}: {_truncate(content.strip(), 1_000)}")
    return _truncate("\n\n".join(parts), _TASK_CONTEXT_CAP)


def _format_results(
    results: list[_SubagentResult],
    *,
    synthesis_instructions: str | None,
) -> str:
    lines: list[str] = []
    if synthesis_instructions:
        lines.append(f"Synthesis instructions: {synthesis_instructions.strip()}")
        lines.append("")
    lines.append("Subagent results:")
    for result in results:
        status = "ok" if result.ok else "failed"
        lines.append(f"\n{result.index}. {result.title} [{result.kind}, {status}, {result.latency_ms}ms]")
        if result.error:
            lines.append(f"Error: {result.error}")
        if result.tool_summaries:
            lines.append("Tools used:")
            lines.extend(f"- {summary}" for summary in result.tool_summaries)
        lines.append("Findings:")
        lines.append(_truncate(result.output.strip(), _WORKER_OUTPUT_CAP) or "(none)")
    return "\n".join(lines).strip()


def _result(
    *,
    index: int,
    task: SubagentTask,
    started: float,
    ok: bool,
    output: str,
    tool_summaries: list[str],
    error: str | None = None,
) -> _SubagentResult:
    return _SubagentResult(
        index=index,
        title=task.title,
        kind=task.kind,
        ok=ok,
        output=output,
        latency_ms=int((time.monotonic() - started) * 1000),
        tool_summaries=tool_summaries,
        error=error,
    )


def _truncate(text: str, cap: int) -> str:
    if len(text.encode("utf-8")) <= cap:
        return text
    return text[: cap // 2] + "\n...[truncated]..."


def _short(text: str, *, limit: int = 200) -> str:
    text = text.strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 3] + "..."
