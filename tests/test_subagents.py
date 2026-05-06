from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from agent.providers.base import (
    LLMFinish,
    LLMTextDelta,
    ProviderEvent,
    ProviderMessage,
    ToolSchema,
)
from agent.subagents import (
    DelegateSubagentsArgs,
    SubagentSettings,
    make_delegation_tool,
)
from agent.tools.base import ToolContext, validate_args


def test_delegation_tool_runs_children_with_configured_cap() -> None:
    llm = _CountingLLM()
    tool = make_delegation_tool(
        llm=llm,
        system_prompt="Be useful.",
        parent_messages=[ProviderMessage(role="user", content="compare options")],
        worker_tools=[],
        model="test-model",
        temperature=0,
        max_tokens=None,
        thinking_enabled=False,
        settings=SubagentSettings(max_children=2, max_iters=1, timeout_s=5, tool_timeout_s=1),
    )
    args = validate_args(
        tool,
        {
            "tasks": [
                {"title": "A", "instructions": "Do A"},
                {"title": "B", "instructions": "Do B"},
            ]
        },
    )

    result = asyncio.run(tool.handler(args, ToolContext(conversation_id="c1", call_id="call1")))

    assert "1. A" in result.output
    assert "2. B" in result.output
    assert llm.max_active == 2


def test_delegation_args_allow_at_most_four_tasks() -> None:
    error = None
    try:
        DelegateSubagentsArgs.model_validate({
            "tasks": [
                {"title": str(i), "instructions": "work"}
                for i in range(5)
            ]
        })
    except Exception as exc:  # pydantic raises ValidationError
        error = exc

    assert error is not None


class _CountingLLM:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0

    async def stream(
        self,
        *,
        system: str,
        messages: list[ProviderMessage],
        tools: list[ToolSchema],
        model: str,
        temperature: float = 0.3,
        max_tokens: int | None = None,
        thinking_enabled: bool = True,
    ) -> AsyncIterator[ProviderEvent]:
        del system, tools, model, temperature, max_tokens, thinking_enabled
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.01)
            yield LLMTextDelta(text=f"done: {messages[-1].content}")
            yield LLMFinish(reason="stop")
        finally:
            self.active -= 1

    async def aclose(self) -> None:
        return None
