from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID

from dotenv import load_dotenv

from agent.config import AgentConfig, VoiceConfig, load_agent_config
from agent.db.pool import close_pool, create_pool
from agent.db.repo import AgentRepo
from agent.events import AckEvent, DoneEvent, ErrorEvent, TextDelta
from agent.mcp.registry import MCPRegistry
from agent.providers.factory import make_provider
from agent.runtime import AgentRuntime
from agent.tools.base import ToolRegistry
from voice.livekit_models import (
    build_livekit_llm,
    build_livekit_stt,
    build_livekit_tts,
    build_livekit_turn_detection,
    build_livekit_vad,
)

log = logging.getLogger("voice.livekit_agent")


class ExaminerLiveKitAgent:
    """LiveKit Agent wrapper around the existing Examiner runtime.

    The class is created dynamically after importing LiveKit so normal test
    runs can import this module without LiveKit installed.
    """


def _make_agent_class(livekit_agent_base: type) -> type:
    class RuntimeBackedAgent(livekit_agent_base):
        def __init__(
            self,
            *,
            cfg: AgentConfig,
            runtime: AgentRuntime,
            voice_config: VoiceConfig,
            conversation_id: UUID | None,
            user_id: str | None,
        ) -> None:
            super().__init__(instructions=cfg.system_prompt)
            self._cfg = cfg
            self._runtime = runtime
            self._voice_config = voice_config
            self._conversation_id = conversation_id
            self._user_id = user_id

        async def llm_node(
            self,
            chat_ctx: Any,
            tools: list[Any],
            model_settings: Any,
        ) -> AsyncIterator[Any]:
            if self._voice_config.llm.provider != "runtime":
                async for chunk in super().llm_node(chat_ctx, tools, model_settings):
                    yield chunk
                return

            text = _latest_user_text(chat_ctx)
            if not text:
                return
            async for event in self._runtime.run_turn(
                user_text=text,
                conversation_id=self._conversation_id,
                user_id=self._user_id,
            ):
                if isinstance(event, AckEvent):
                    yield event.text
                elif isinstance(event, TextDelta):
                    yield event.text
                elif isinstance(event, ErrorEvent):
                    yield _spoken_error(event)
                elif isinstance(event, DoneEvent):
                    self._conversation_id = event.conversation_id

    return RuntimeBackedAgent


async def run_job(ctx: Any) -> None:
    load_dotenv()
    logging.basicConfig(
        level=os.environ.get("VOICE_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        from livekit.agents import Agent, AgentSession
    except ImportError as e:  # pragma: no cover - only exercised without optional deps
        raise RuntimeError("Install the voice-livekit extra to run the LiveKit agent") from e

    metadata = _metadata_from_job(ctx)
    cfg = await _load_job_config(metadata)
    voice_config = _voice_config_for_job(cfg, metadata)
    pool = await create_pool()
    tools = ToolRegistry()
    mcp = MCPRegistry(tools)
    llm_client = None
    try:
        await mcp.start(cfg.mcp_servers)
        llm_client = make_provider(cfg.provider)
        runtime = AgentRuntime(cfg=cfg, pool=pool, llm=llm_client, tools=tools)
        agent_cls = _make_agent_class(Agent)
        agent = agent_cls(
            cfg=cfg,
            runtime=runtime,
            voice_config=voice_config,
            conversation_id=_uuid_or_none(metadata.get("conversation_id")),
            user_id=_str_or_none(metadata.get("user_id")),
        )
        session = AgentSession(
            stt=build_livekit_stt(voice_config),
            llm=build_livekit_llm(voice_config),
            tts=build_livekit_tts(voice_config),
            vad=build_livekit_vad(voice_config),
            turn_detection=build_livekit_turn_detection(voice_config),
            preemptive_generation=voice_config.turn_detection.preemptive_generation,
        )

        await ctx.connect()
        await session.start(agent=agent, room=ctx.room)
    finally:
        await mcp.aclose()
        if llm_client is not None:
            await llm_client.aclose()
        await close_pool(pool)


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=os.environ.get("VOICE_LOG_LEVEL", "INFO"))

    try:
        from livekit.agents import AgentServer
    except ImportError:
        AgentServer = None  # type: ignore[assignment]

    if AgentServer is not None:
        server = AgentServer()

        @server.rtc_session(agent_name=os.environ.get("LIVEKIT_AGENT_NAME", "examiner-agent"))
        async def _rtc_session(ctx: Any) -> None:
            await run_job(ctx)

        server.run()
        return

    try:
        from livekit.agents import WorkerOptions, cli
    except ImportError as e:  # pragma: no cover - only exercised without optional deps
        raise RuntimeError("Install the voice-livekit extra to run the LiveKit agent") from e
    cli.run_app(WorkerOptions(entrypoint_fnc=run_job))


def _metadata_from_job(ctx: Any) -> dict[str, Any]:
    raw = (
        getattr(getattr(ctx, "job", None), "metadata", None)
        or getattr(ctx, "metadata", None)
        or "{}"
    )
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            log.warning("ignoring invalid LiveKit job metadata: %s", raw[:200])
    return {}


async def _load_job_config(metadata: dict[str, Any]) -> AgentConfig:
    config_path = metadata.get("config_path") or os.environ.get("AGENT_CONFIG", "config/agent.yaml")
    base = load_agent_config(_safe_config_path(str(config_path)))
    agent_id = _str_or_none(metadata.get("agent_id"))
    if not agent_id or not os.environ.get("SUPABASE_URL"):
        return base

    pool = await create_pool()
    try:
        row = await AgentRepo(pool).get(agent_id)
    finally:
        await close_pool(pool)
    if row is None:
        log.warning("LiveKit requested unknown agent_id=%s; using config file", agent_id)
        return base
    data = _json_object(row["agent_config"])
    if not data:
        data = base.model_dump(mode="json")
    data.update(
        {
            "agent_id": row["id"],
            "system_prompt": row["system_prompt"],
            "provider": row["provider"],
            "model": row["model"],
            "temperature": row["temperature"],
            "max_tokens": row["max_tokens"],
            "history_limit": row["history_limit"],
            "tool_groups": list(row["tool_groups"] or []),
            "ack": _json_object(row["ack"]),
            "mcp_servers": _json_list(row["mcp_servers"]),
            "timeouts": _json_object(row["timeouts"]),
            "tracing": _json_object(row["tracing"]),
            "voice": _json_object(row["voice_config"]) or base.voice.model_dump(mode="json"),
        }
    )
    thinking_enabled = metadata.get("thinking_enabled")
    if isinstance(thinking_enabled, bool):
        data["thinking_enabled"] = thinking_enabled
    return AgentConfig.model_validate(data)


def _voice_config_for_job(cfg: AgentConfig, metadata: dict[str, Any]) -> VoiceConfig:
    data = cfg.voice.model_dump(mode="json")
    voice = metadata.get("voice")
    if isinstance(voice, dict):
        data.update(voice)
    if os.environ.get("LIVEKIT_URL"):
        data.setdefault("livekit", {})["url"] = os.environ["LIVEKIT_URL"]
    if os.environ.get("LIVEKIT_AGENT_NAME"):
        data.setdefault("livekit", {})["agent_name"] = os.environ["LIVEKIT_AGENT_NAME"]
    return VoiceConfig.model_validate(data)


def _latest_user_text(chat_ctx: Any) -> str | None:
    messages = getattr(chat_ctx, "messages", None) or getattr(chat_ctx, "items", None) or []
    for message in reversed(list(messages)):
        role = getattr(message, "role", None)
        if role != "user":
            continue
        content = getattr(message, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            text = " ".join(
                item for item in content
                if isinstance(item, str) and item.strip()
            ).strip()
            if text:
                return text
    return None


def _spoken_error(event: ErrorEvent) -> str:
    if event.kind in {"provider", "provider_stream"}:
        return "The model provider is having trouble right now. Please try again in a moment."
    return "I hit an internal error. Please try again."


def _str_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _json_object(value: Any) -> dict[str, Any]:
    loaded = _json_value(value)
    return loaded if isinstance(loaded, dict) else {}


def _json_list(value: Any) -> list[Any]:
    loaded = _json_value(value)
    return loaded if isinstance(loaded, list) else []


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str) and value.strip():
        return json.loads(value)
    return value


def _uuid_or_none(value: Any) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str) and value.strip():
        return UUID(value)
    return None


def _safe_config_path(path: str) -> Path:
    root = Path.cwd().resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    config_root = (root / "config").resolve()
    if candidate != config_root and config_root not in candidate.parents:
        raise ValueError("agent config path must be under the config/ directory")
    return candidate


if __name__ == "__main__":
    main()
