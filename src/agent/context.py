from __future__ import annotations

from .db.repo import Message
from .providers.base import ProviderMessage, ProviderToolCall


def build_system_prompt(agent_prompt: str) -> str:
    """Pass the agent's system prompt through verbatim.

    The runtime intentionally does not shape behavior — what the LLM
    produces is what gets streamed downstream. If a deployment wants
    ack-aware phrasing (e.g. "don't say 'sure' since the user just heard
    it"), that's the agent author's call and belongs in their prompt.
    """
    return agent_prompt.strip()


def build_messages(history: list[Message]) -> list[ProviderMessage]:
    """Translate persisted messages into provider-shaped messages.

    `ack` rows are skipped — they are spoken-only and re-feeding them to the
    LLM would teach it to imitate them. `error` and `system` rows are also
    skipped from the chat context.
    """
    out: list[ProviderMessage] = []
    pending_assistant_text: list[str] = []
    pending_assistant_tool_calls: list[ProviderToolCall] = []

    def flush_assistant() -> None:
        if not pending_assistant_text and not pending_assistant_tool_calls:
            return
        out.append(ProviderMessage(
            role="assistant",
            content="".join(pending_assistant_text) or None,
            tool_calls=list(pending_assistant_tool_calls),
        ))
        pending_assistant_text.clear()
        pending_assistant_tool_calls.clear()

    for m in history:
        if m.kind in ("ack", "error", "system"):
            continue
        if m.kind == "user_text":
            flush_assistant()
            out.append(ProviderMessage(role="user", content=m.content or ""))
        elif m.kind == "assistant_text":
            pending_assistant_text.append(m.content or "")
        elif m.kind == "tool_call":
            payload = m.content_json or {}
            pending_assistant_tool_calls.append(ProviderToolCall(
                call_id=m.tool_call_id or "",
                name=m.tool_name or "",
                args=payload.get("args", {}) if isinstance(payload, dict) else {},
            ))
        elif m.kind == "tool_result":
            flush_assistant()
            out.append(ProviderMessage(
                role="tool",
                content=m.content or "",
                tool_call_id=m.tool_call_id or "",
            ))
    flush_assistant()
    return out
