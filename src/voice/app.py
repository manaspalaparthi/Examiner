from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from agent.config import (
    AckConfig,
    AgentConfig,
    BargeInConfig,
    STTConfig,
    TTSConfig,
    TimeoutsConfig,
    TracingConfig,
    VADConfig,
    VoiceConfig,
    load_agent_config,
)
from agent.db.pool import close_pool, create_pool
from agent.db.repo import AgentRepo, ConversationViewRepo
from agent.events import AckEvent, DoneEvent as RuntimeDoneEvent, ErrorEvent, ThinkingDelta, TextDelta, ToolEnd, ToolStart
from agent.errors import ConfigError
from agent.mcp.registry import MCPRegistry
from agent.providers.factory import make_provider
from agent.runtime import AgentRuntime
from agent.tools.base import ToolRegistry

from .agent_registry import build_agent, registered_agents
from .stt import ParakeetSTT
from .tts import KokoroTTS

log = logging.getLogger("voice.app")


class VoiceStartRequest(BaseModel):
    type: str = "start"
    agent: str = "runtime"
    agent_config: dict[str, Any] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    voice_config: VoiceConfig = Field(default_factory=VoiceConfig)


class RuntimeConfigSaveRequest(BaseModel):
    config: AgentConfig
    path: str | None = None


class AgentChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message: str
    conversation_id: UUID | None = Field(default=None, alias="conversationId")
    user_id: str | None = Field(default=None, alias="userId")
    thinking_enabled: bool | None = Field(default=None, alias="thinkingEnabled")


class AgentChatResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    conversation_id: UUID | None = Field(default=None, alias="conversationId")
    message_id: UUID | None = Field(default=None, alias="messageId")
    message: str
    total_ms: int | None = Field(default=None, alias="totalMs")


AgentStatus = Literal["active", "draft", "archived"]


class AgentRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    user_id: str = Field(default="admin", alias="userId")
    name: str
    description: str = ""
    status: AgentStatus = "draft"
    backend_agent: str = Field(default="runtime", alias="backendAgent")
    config_path: str | None = Field(default=None, alias="configPath")
    voice_id: str = Field(default="af_heart", alias="voiceId")
    provider: str
    model: str
    system_prompt: str = Field(default="", alias="systemPrompt")
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, alias="maxTokens")
    history_limit: int = Field(default=30, alias="historyLimit")
    tools: list[str] = Field(default_factory=list)
    tool_groups: list[str] = Field(default_factory=list, alias="toolGroups")
    ack: dict[str, Any] = Field(default_factory=dict)
    mcp_servers: list[dict[str, Any]] = Field(default_factory=list, alias="mcpServers")
    timeouts: dict[str, Any] = Field(default_factory=dict)
    tracing: dict[str, Any] = Field(default_factory=dict)
    voice_config: dict[str, Any] = Field(default_factory=dict, alias="voiceConfig")
    agent_config: dict[str, Any] = Field(default_factory=dict, alias="agentConfig")
    start_params: dict[str, Any] = Field(default_factory=dict, alias="startParams")
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class AgentCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    user_id: str = Field(default="admin", alias="userId")
    name: str
    description: str = ""
    status: AgentStatus = "active"
    backend_agent: str = Field(default="runtime", alias="backendAgent")
    config_path: str | None = Field(default=None, alias="configPath")
    voice_id: str = Field(default="af_heart", alias="voiceId")
    provider: str | None = None
    model: str | None = None
    system_prompt: str = Field(default="", alias="systemPrompt")
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, alias="maxTokens")
    history_limit: int = Field(default=30, alias="historyLimit")
    tools: list[str] = Field(default_factory=list)
    tool_groups: list[str] = Field(default_factory=list, alias="toolGroups")
    ack: dict[str, Any] = Field(default_factory=dict)
    mcp_servers: list[dict[str, Any]] = Field(default_factory=list, alias="mcpServers")
    timeouts: dict[str, Any] = Field(default_factory=dict)
    tracing: dict[str, Any] = Field(default_factory=dict)
    voice_config: dict[str, Any] = Field(default_factory=dict, alias="voiceConfig")
    agent_config: dict[str, Any] = Field(default_factory=dict, alias="agentConfig")
    start_params: dict[str, Any] = Field(default_factory=dict, alias="startParams")
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user_id: str | None = Field(default=None, alias="userId")
    name: str | None = None
    description: str | None = None
    status: AgentStatus | None = None
    backend_agent: str | None = Field(default=None, alias="backendAgent")
    config_path: str | None = Field(default=None, alias="configPath")
    voice_id: str | None = Field(default=None, alias="voiceId")
    provider: str | None = None
    model: str | None = None
    system_prompt: str | None = Field(default=None, alias="systemPrompt")
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, alias="maxTokens")
    history_limit: int | None = Field(default=None, alias="historyLimit")
    tools: list[str] | None = None
    tool_groups: list[str] | None = Field(default=None, alias="toolGroups")
    ack: dict[str, Any] | None = None
    mcp_servers: list[dict[str, Any]] | None = Field(default=None, alias="mcpServers")
    timeouts: dict[str, Any] | None = None
    tracing: dict[str, Any] | None = None
    voice_config: dict[str, Any] | None = Field(default=None, alias="voiceConfig")
    agent_config: dict[str, Any] | None = Field(default=None, alias="agentConfig")
    start_params: dict[str, Any] | None = Field(default=None, alias="startParams")
    metadata: dict[str, Any] | None = None


class VoiceResourceStatus(BaseModel):
    key: str
    loaded: bool


class VoiceResourceManager:
    def __init__(self) -> None:
        self._stt: dict[str, ParakeetSTT] = {}
        self._tts: dict[str, KokoroTTS] = {}
        self._lock = asyncio.Lock()

    async def get_stt(self, cfg: STTConfig) -> ParakeetSTT:
        key = self._stt_key(cfg)
        async with self._lock:
            stt = self._stt.get(key)
            if stt is None:
                stt = ParakeetSTT(model_id=cfg.model_id)
                self._stt[key] = stt
        await stt.load()
        return stt

    async def get_tts(self, cfg: TTSConfig) -> KokoroTTS:
        key = self._tts_key(cfg)
        async with self._lock:
            tts = self._tts.get(key)
            if tts is None:
                tts = KokoroTTS(
                    model_path=cfg.model_path,
                    voices_path=cfg.voices_path,
                    voice=cfg.voice,
                    speed=cfg.speed,
                    lang=cfg.lang,
                )
                self._tts[key] = tts
        await tts.load()
        return tts

    def default_loaded(self, cfg: VoiceConfig) -> tuple[bool, bool]:
        stt = self._stt.get(self._stt_key(cfg.stt))
        tts = self._tts.get(self._tts_key(cfg.tts))
        return bool(stt and stt.loaded), bool(tts and tts.loaded)

    def status(self) -> dict[str, list[VoiceResourceStatus]]:
        return {
            "stt": [
                VoiceResourceStatus(key=key, loaded=resource.loaded)
                for key, resource in sorted(self._stt.items())
            ],
            "tts": [
                VoiceResourceStatus(key=key, loaded=resource.loaded)
                for key, resource in sorted(self._tts.items())
            ],
        }

    @staticmethod
    def _stt_key(cfg: STTConfig) -> str:
        return cfg.model_id or ParakeetSTT._default_model_id()

    @staticmethod
    def _tts_key(cfg: TTSConfig) -> str:
        return json.dumps(
            {
                "model_path": cfg.model_path,
                "voices_path": cfg.voices_path,
            },
            sort_keys=True,
        )


_resources = VoiceResourceManager()
_default_voice_config = VoiceConfig()
_db_pool: Any | None = None
_admin_user_id: str | None = None


def _cors_origins_from_env() -> list[str]:
    raw = os.environ.get(
        "VOICE_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001",
    )
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _admin_user_id, _db_pool, _default_voice_config
    load_dotenv()
    logging.basicConfig(
        level=os.environ.get("VOICE_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _default_voice_config = _voice_config_from_env()
    if os.environ.get("SUPABASE_URL"):
        try:
            _db_pool = await create_pool()
            _admin_user_id = await _ensure_admin_user()
            await _ensure_default_agent_record()
            log.info("supabase ready")
        except Exception as e:
            _db_pool = None
            _admin_user_id = None
            log.warning("supabase unavailable; agent CRUD endpoints will return 503: %s", e)
    if _env_bool("VOICE_PRELOAD_MODELS", default=False):
        log.info("loading default STT and TTS models; first call may take a while")
        await _resources.get_stt(_default_voice_config.stt)
        await _resources.get_tts(_default_voice_config.tts)
        log.info("default voice models loaded")
    try:
        yield
    finally:
        if _db_pool is not None:
            await close_pool(_db_pool)
            _db_pool = None


app = FastAPI(
    title="Examiner Agent + Voice API",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins_from_env(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    stt_loaded, tts_loaded = _resources.default_loaded(_default_voice_config)
    return {
        "ok": True,
        "stt_loaded": stt_loaded,
        "tts_loaded": tts_loaded,
        "resources": _resources.status(),
    }


@app.get("/api/voice/capabilities")
async def voice_capabilities() -> dict[str, Any]:
    return {
        "agents": registered_agents(),
        "default_agent": "runtime",
        "websocket_path": "/ws/voice",
        "input_audio": {
            "encoding": "pcm_s16le",
            "sample_rate": 16_000,
            "channels": 1,
            "frame_ms": 20,
            "frame_bytes": 640,
        },
        "output_audio": {
            "encoding": "pcm_s16le",
            "sample_rate": KokoroTTS.SAMPLE_RATE,
            "channels": 1,
            "frame_ms": KokoroTTS.FRAME_MS,
        },
        "voice_config_schema": VoiceConfig.model_json_schema(),
        "agent_start_schema": VoiceStartRequest.model_json_schema(),
    }


@app.get("/api/voice/config")
async def get_default_voice_config() -> VoiceConfig:
    return _default_voice_config


@app.post("/api/voice/config/validate")
async def validate_voice_config(config: VoiceConfig) -> VoiceConfig:
    return config


@app.post("/api/voice/start/validate")
async def validate_voice_start(request: VoiceStartRequest) -> VoiceStartRequest:
    _validate_agent_name(request.agent)
    return request


@app.get("/api/agents/runtime/config")
async def get_runtime_config(path: str | None = Query(default=None)) -> AgentConfig:
    try:
        return load_agent_config(_safe_config_path(path))
    except ConfigError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/api/agents/runtime/config/validate")
async def validate_runtime_config(config: AgentConfig) -> AgentConfig:
    return config


@app.put("/api/agents/runtime/config")
async def save_runtime_config(request: RuntimeConfigSaveRequest) -> AgentConfig:
    path = _safe_config_path(request.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            request.config.model_dump(mode="json"),
            f,
            sort_keys=False,
            allow_unicode=False,
        )
    return load_agent_config(path)


@app.get("/api/agents", response_model=list[AgentRecord])
async def list_agents() -> list[AgentRecord]:
    repo = AgentRepo(_require_db())
    rows = await repo.list()
    return [_agent_from_row(row) for row in rows]


@app.post("/api/agents", response_model=AgentRecord, status_code=201)
async def create_agent(request: AgentCreateRequest) -> AgentRecord:
    repo = AgentRepo(_require_db())
    if not request.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    agent_id = request.id or _slugify_agent_id(request.name)
    provider = request.provider or _infer_provider(request.model)
    model = request.model or os.environ.get("MODEL_NAME") or "gemini-2.5-flash"
    ack = request.ack or AckConfig().model_dump(mode="json")
    timeouts = request.timeouts or TimeoutsConfig().model_dump(mode="json")
    tracing = request.tracing or TracingConfig().model_dump(mode="json")
    voice_config = request.voice_config or _default_voice_config.model_dump(mode="json")
    agent_config = request.agent_config or {
        "agent_id": agent_id,
        "system_prompt": request.system_prompt,
        "provider": provider,
        "model": model,
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
        "history_limit": request.history_limit,
        "tool_groups": request.tool_groups,
        "ack": ack,
        "mcp_servers": request.mcp_servers,
        "timeouts": timeouts,
        "tracing": tracing,
    }
    payload = {
        "id": agent_id,
        "user_id": _owner_user_id(request.user_id),
        "name": request.name.strip(),
        "description": request.description,
        "status": request.status,
        "backend_agent": request.backend_agent,
        "config_path": request.config_path,
        "voice_id": request.voice_id,
        "provider": provider,
        "model": model,
        "system_prompt": request.system_prompt,
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
        "history_limit": request.history_limit,
        "tools": request.tools,
        "tool_groups": request.tool_groups,
        "ack": ack,
        "mcp_servers": request.mcp_servers,
        "timeouts": timeouts,
        "tracing": tracing,
        "voice_config": voice_config,
        "agent_config": agent_config,
        "start_params": request.start_params,
        "metadata": request.metadata,
    }
    try:
        row = await repo.create(payload)
    except Exception as e:
        raise HTTPException(status_code=409, detail=f"Agent {agent_id!r} already exists") from e
    return _agent_from_row(row)


@app.get("/api/agents/{agent_id}", response_model=AgentRecord)
async def get_agent(agent_id: str) -> AgentRecord:
    row = await AgentRepo(_require_db()).get(agent_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _agent_from_row(row)


@app.post("/api/agents/{agent_id}/chat", response_model=AgentChatResponse)
async def chat_with_agent(agent_id: str, request: AgentChatRequest) -> AgentChatResponse:
    pool = _require_db()
    row = await AgentRepo(pool).get(agent_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent = _agent_from_row(row)
    if agent.status == "archived":
        raise HTTPException(status_code=400, detail="Archived agents cannot be tested")
    if agent.backend_agent != "runtime":
        raise HTTPException(
            status_code=400,
            detail=f"Playground chat currently supports runtime agents, got {agent.backend_agent!r}",
        )

    text = request.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="message is required")

    cfg = _agent_runtime_config(agent, thinking_enabled=request.thinking_enabled)
    tools = ToolRegistry()
    mcp = MCPRegistry(tools)
    llm = make_provider(cfg.provider)
    chunks: list[str] = []
    conversation_id: UUID | None = request.conversation_id
    message_id: UUID | None = None
    total_ms: int | None = None
    try:
        await mcp.start(cfg.mcp_servers)
        runtime = AgentRuntime(cfg=cfg, pool=pool, llm=llm, tools=tools)
        async for event in runtime.run_turn(
            user_text=text,
            conversation_id=request.conversation_id,
            user_id=request.user_id or agent.user_id,
        ):
            if isinstance(event, AckEvent):
                chunks.append(f"{event.text.strip()}\n\n")
            elif isinstance(event, TextDelta):
                chunks.append(event.text)
            elif isinstance(event, ErrorEvent):
                chunks.append(f"I hit an error: {event.message}")
            elif isinstance(event, RuntimeDoneEvent):
                conversation_id = event.conversation_id
                message_id = event.message_id
                total_ms = event.total_ms
    finally:
        await mcp.aclose()
        await llm.aclose()

    return AgentChatResponse(
        conversation_id=conversation_id,
        message_id=message_id,
        message="".join(chunks).strip(),
        total_ms=total_ms,
    )


@app.post("/api/agents/{agent_id}/chat/stream")
async def stream_chat_with_agent(agent_id: str, request: AgentChatRequest) -> StreamingResponse:
    pool = _require_db()
    row = await AgentRepo(pool).get(agent_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent = _agent_from_row(row)
    if agent.status == "archived":
        raise HTTPException(status_code=400, detail="Archived agents cannot be tested")
    if agent.backend_agent != "runtime":
        raise HTTPException(
            status_code=400,
            detail=f"Playground chat currently supports runtime agents, got {agent.backend_agent!r}",
        )

    text = request.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="message is required")

    cfg = _agent_runtime_config(agent, thinking_enabled=request.thinking_enabled)

    async def events():
        tools = ToolRegistry()
        mcp = MCPRegistry(tools)
        llm = None
        try:
            llm = make_provider(cfg.provider)
            await mcp.start(cfg.mcp_servers)
            runtime = AgentRuntime(cfg=cfg, pool=pool, llm=llm, tools=tools)
            async for event in runtime.run_turn(
                user_text=text,
                conversation_id=request.conversation_id,
                user_id=request.user_id or agent.user_id,
            ):
                yield _chat_stream_line(event)
        except Exception as e:
            log.exception("streaming playground chat failed")
            yield _json_line({
                "type": "error",
                "kind": "internal",
                "message": str(e) or "Runtime chat failed",
            })
        finally:
            await mcp.aclose()
            if llm is not None:
                await llm.aclose()

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.patch("/api/agents/{agent_id}", response_model=AgentRecord)
async def update_agent(agent_id: str, request: AgentUpdateRequest) -> AgentRecord:
    repo = AgentRepo(_require_db())
    current = await repo.get(agent_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    current_agent = _agent_from_row(current)
    update = request.model_dump(exclude_unset=True, by_alias=False)
    provider = update.get("provider", current_agent.provider)
    model = update.get("model", current_agent.model)
    system_prompt = update.get("system_prompt", current_agent.system_prompt)
    temperature = update.get("temperature", current_agent.temperature)
    max_tokens = update.get("max_tokens", current_agent.max_tokens)
    history_limit = update.get("history_limit", current_agent.history_limit)
    tool_groups = update.get("tool_groups", current_agent.tool_groups)
    ack = update.get("ack", current_agent.ack)
    mcp_servers = update.get("mcp_servers", current_agent.mcp_servers)
    timeouts = update.get("timeouts", current_agent.timeouts)
    tracing = update.get("tracing", current_agent.tracing)
    agent_config = update.get("agent_config") or {
        **current_agent.agent_config,
        "agent_id": agent_id,
        "system_prompt": system_prompt,
        "provider": provider,
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "history_limit": history_limit,
        "tool_groups": tool_groups,
        "ack": ack,
        "mcp_servers": mcp_servers,
        "timeouts": timeouts,
        "tracing": tracing,
    }

    row = await repo.update(
        agent_id,
        {
            "name": update.get("name", current_agent.name),
            "user_id": _owner_user_id(update.get("user_id", current_agent.user_id)),
            "description": update.get("description", current_agent.description),
            "status": update.get("status", current_agent.status),
            "backend_agent": update.get("backend_agent", current_agent.backend_agent),
            "config_path": update.get("config_path", current_agent.config_path),
            "voice_id": update.get("voice_id", current_agent.voice_id),
            "provider": provider,
            "model": model,
            "system_prompt": system_prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "history_limit": history_limit,
            "tools": update.get("tools", current_agent.tools),
            "tool_groups": tool_groups,
            "ack": ack,
            "mcp_servers": mcp_servers,
            "timeouts": timeouts,
            "tracing": tracing,
            "voice_config": update.get("voice_config", current_agent.voice_config),
            "agent_config": agent_config,
            "start_params": update.get("start_params", current_agent.start_params),
            "metadata": update.get("metadata", current_agent.metadata),
        },
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _agent_from_row(row)


@app.delete("/api/agents/{agent_id}", status_code=204)
async def delete_agent(agent_id: str) -> None:
    deleted = await AgentRepo(_require_db()).delete(agent_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Agent not found")


@app.get("/api/conversations")
async def list_conversations(
    agent_id: str | None = Query(default=None, alias="agentId"),
    status: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    return await ConversationViewRepo(_require_db()).list(agent_id=agent_id, status=status)


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: UUID) -> dict[str, Any]:
    row = await ConversationViewRepo(_require_db()).get(conversation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return row


@app.websocket("/ws/voice")
async def ws_voice(ws: WebSocket) -> None:
    await ws.accept()
    try:
        first = await ws.receive_text()
        try:
            request = VoiceStartRequest.model_validate_json(first)
        except Exception as e:
            await ws.close(code=1003, reason=f"invalid start frame: {e}")
            return
        if request.type != "start":
            await ws.close(code=1003, reason="expected {type:'start'} as first frame")
            return
        if request.agent not in registered_agents():
            await ws.close(
                code=1003,
                reason=f"unknown agent backend: {request.agent}",
            )
            return

        agent = build_agent(request.agent, request.agent_config)
        stt = await _resources.get_stt(request.voice_config.stt)
        tts = await _resources.get_tts(request.voice_config.tts)
        from .session import VoiceSession
        from .vad import SileroVAD

        vad = SileroVAD(**request.voice_config.vad.model_dump())
        session = VoiceSession(
            ws,
            vad,
            stt,
            tts,
            agent,
            initial_params=request.params,
            tts_options={
                "voice": request.voice_config.tts.voice,
                "speed": request.voice_config.tts.speed,
                "lang": request.voice_config.tts.lang,
            },
            echo_tail_s=request.voice_config.echo_tail_s,
            barge_in_enabled=request.voice_config.barge_in.enabled,
            barge_in_min_speech_ms=request.voice_config.barge_in.min_speech_ms,
            barge_in_min_rms=request.voice_config.barge_in.min_rms,
        )
        await session.run()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.exception("ws_voice failed: %s", e)
    finally:
        try:
            await ws.close()
        except Exception:
            pass


def _require_db() -> Any:
    if _db_pool is None:
        raise HTTPException(
            status_code=503,
            detail="Supabase is not available. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.",
        )
    return _db_pool


async def _ensure_admin_user() -> str:
    if _db_pool is None:
        raise RuntimeError("Supabase client is not initialized")
    email = os.environ.get("SUPABASE_ADMIN_EMAIL", "admin@example.com")
    password = os.environ.get("SUPABASE_ADMIN_PASSWORD", "admin")
    name = os.environ.get("SUPABASE_ADMIN_NAME", "Admin")

    def find_existing() -> str | None:
        users = _db_pool.auth.admin.list_users()
        for user in getattr(users, "users", users):
            if getattr(user, "email", None) == email:
                return str(user.id)
        return None

    import asyncio

    existing = await asyncio.to_thread(find_existing)
    if existing:
        return existing

    def create() -> str:
        result = _db_pool.auth.admin.create_user(
            {
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {"name": name},
            }
        )
        user = getattr(result, "user", result)
        return str(user.id)

    try:
        return await asyncio.to_thread(create)
    except Exception:
        existing = await asyncio.to_thread(find_existing)
        if existing:
            return existing
        raise


async def _ensure_default_agent_record() -> None:
    if _db_pool is None:
        return
    repo = AgentRepo(_db_pool)
    existing = await repo.count()
    if existing:
        return
    config_path = os.environ.get("AGENT_CONFIG", "config/agent.yaml")
    try:
        cfg = load_agent_config(config_path)
    except ConfigError as e:
        log.warning("skipping default agent seed: %s", e)
        return
    voice_config = _default_voice_config.model_dump(mode="json")
    await repo.create(
        {
            "id": cfg.agent_id,
            "user_id": _owner_user_id(None),
            "name": _humanize_agent_id(cfg.agent_id),
            "description": "Runtime voice agent loaded from config/agent.yaml.",
            "status": "active",
            "backend_agent": "runtime",
            "config_path": config_path,
            "voice_id": voice_config["tts"]["voice"],
            "provider": cfg.provider,
            "model": cfg.model,
            "system_prompt": cfg.system_prompt,
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens,
            "history_limit": cfg.history_limit,
            "tools": [],
            "tool_groups": cfg.tool_groups,
            "ack": cfg.ack.model_dump(mode="json"),
            "mcp_servers": [server.model_dump(mode="json") for server in cfg.mcp_servers],
            "timeouts": cfg.timeouts.model_dump(mode="json"),
            "tracing": cfg.tracing.model_dump(mode="json"),
            "voice_config": voice_config,
            "agent_config": cfg.model_dump(mode="json"),
            "start_params": {},
            "metadata": {"seeded_from": config_path},
        }
    )


def _owner_user_id(value: str | None) -> str:
    if value and _looks_uuid(value):
        return value
    if _admin_user_id:
        return _admin_user_id
    raise HTTPException(status_code=503, detail="Supabase admin user is not ready")


def _looks_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except ValueError:
        return False


def _agent_from_row(row: dict[str, Any]) -> AgentRecord:
    return AgentRecord.model_validate(
        {
            "id": row["id"],
            "user_id": row["user_id"],
            "name": row["name"],
            "description": row["description"],
            "status": row["status"],
            "backend_agent": row["backend_agent"],
            "config_path": row["config_path"],
            "voice_id": row["voice_id"],
            "provider": row["provider"],
            "model": row["model"],
            "system_prompt": row["system_prompt"],
            "temperature": row["temperature"],
            "max_tokens": row["max_tokens"],
            "history_limit": row["history_limit"],
            "tools": list(row["tools"] or []),
            "tool_groups": list(row["tool_groups"] or []),
            "ack": _load_jsonb(row["ack"]) or {},
            "mcp_servers": _load_jsonb(row["mcp_servers"]) or [],
            "timeouts": _load_jsonb(row["timeouts"]) or {},
            "tracing": _load_jsonb(row["tracing"]) or {},
            "voice_config": _load_jsonb(row["voice_config"]) or {},
            "agent_config": _load_jsonb(row["agent_config"]) or {},
            "start_params": _load_jsonb(row["start_params"]) or {},
            "metadata": _load_jsonb(row["metadata"]) or {},
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    )


def _agent_runtime_config(agent: AgentRecord, *, thinking_enabled: bool | None = None) -> AgentConfig:
    data = {
        "agent_id": agent.id,
        "system_prompt": agent.system_prompt,
        "provider": agent.provider,
        "model": agent.model,
        "temperature": agent.temperature,
        "max_tokens": agent.max_tokens,
        "thinking_enabled": thinking_enabled,
        "history_limit": agent.history_limit,
        "tool_groups": agent.tool_groups,
        "ack": agent.ack or AckConfig().model_dump(mode="json"),
        "mcp_servers": agent.mcp_servers,
        "timeouts": agent.timeouts or TimeoutsConfig().model_dump(mode="json"),
        "tracing": agent.tracing or TracingConfig().model_dump(mode="json"),
    }
    if thinking_enabled is None:
        data.pop("thinking_enabled")
    return AgentConfig.model_validate({**(agent.agent_config or {}), **data})


def _load_jsonb(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _dump_jsonb(value: Any) -> str:
    return json.dumps(value if value is not None else {})


def _json_line(payload: dict[str, Any]) -> str:
    return json.dumps(payload, default=str, separators=(",", ":")) + "\n"


def _chat_stream_line(event: Any) -> str:
    if isinstance(event, AckEvent):
        return _json_line({"type": "text_delta", "text": f"{event.text.strip()}\n\n"})
    if isinstance(event, TextDelta):
        return _json_line({"type": "text_delta", "text": event.text})
    if isinstance(event, ThinkingDelta):
        return _json_line({"type": "thinking_delta", "text": event.text})
    if isinstance(event, ToolStart):
        return _json_line({
            "type": "tool_start",
            "callId": event.call_id,
            "name": event.tool_name,
            "args": event.args,
            "server": event.server,
        })
    if isinstance(event, ToolEnd):
        return _json_line({
            "type": "tool_end",
            "callId": event.call_id,
            "name": event.tool_name,
            "ok": event.ok,
            "latencyMs": event.latency_ms,
            "summary": event.summary,
            "error": event.error,
        })
    if isinstance(event, ErrorEvent):
        return _json_line({"type": "error", "kind": event.kind, "message": event.message})
    if isinstance(event, RuntimeDoneEvent):
        return _json_line({
            "type": "done",
            "conversationId": str(event.conversation_id),
            "messageId": str(event.message_id) if event.message_id else None,
            "totalMs": event.total_ms,
        })
    return _json_line({"type": "unknown"})


def _slugify_agent_id(name: str) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return f"agt-{stem or 'agent'}"


def _humanize_agent_id(agent_id: str) -> str:
    return agent_id.replace("_", " ").replace("-", " ").strip().title() or "Default Agent"


def _infer_provider(model: str | None) -> str:
    if os.environ.get("MODEL_PROVIDER"):
        return os.environ["MODEL_PROVIDER"]
    if model and model.lower().startswith(("llama", "mistral", "qwen", "phi", "ollama")):
        return "ollama"
    return "gemini"


def _validate_agent_name(name: str) -> None:
    if name not in registered_agents():
        raise HTTPException(
            status_code=400,
            detail=f"Unknown agent backend {name!r}. Registered: {registered_agents()}",
        )


def _voice_config_from_env() -> VoiceConfig:
    try:
        base = load_agent_config().voice
    except Exception as e:
        log.warning("falling back to default voice config: %s", e)
        base = VoiceConfig()

    data = base.model_dump(mode="json")
    if os.environ.get("VOICE_TRANSPORT"):
        data["transport"] = os.environ["VOICE_TRANSPORT"]
    if os.environ.get("PARAKEET_MODEL"):
        data.setdefault("stt", {})["model_id"] = os.environ["PARAKEET_MODEL"]
        data["stt"]["provider"] = "local"
    if os.environ.get("KOKORO_MODEL"):
        data.setdefault("tts", {})["model_path"] = os.environ["KOKORO_MODEL"]
        data["tts"]["provider"] = "local"
    if os.environ.get("KOKORO_VOICES"):
        data.setdefault("tts", {})["voices_path"] = os.environ["KOKORO_VOICES"]
        data["tts"]["provider"] = "local"
    if os.environ.get("KOKORO_VOICE"):
        data.setdefault("tts", {})["voice"] = os.environ["KOKORO_VOICE"]
        data["tts"]["provider"] = "local"
    if os.environ.get("KOKORO_SPEED"):
        data.setdefault("tts", {})["speed"] = float(os.environ["KOKORO_SPEED"])
        data["tts"]["provider"] = "local"
    if os.environ.get("KOKORO_LANG"):
        data.setdefault("tts", {})["lang"] = os.environ["KOKORO_LANG"]
        data["tts"]["provider"] = "local"
    if os.environ.get("VAD_THRESHOLD"):
        data.setdefault("vad", {})["threshold"] = float(os.environ["VAD_THRESHOLD"])
    if os.environ.get("VAD_MIN_SILENCE_MS"):
        data.setdefault("vad", {})["min_silence_ms"] = int(os.environ["VAD_MIN_SILENCE_MS"])
    if os.environ.get("VAD_SPEECH_PAD_MS"):
        data.setdefault("vad", {})["speech_pad_ms"] = int(os.environ["VAD_SPEECH_PAD_MS"])
    if os.environ.get("VAD_MAX_UTTERANCE_S"):
        data.setdefault("vad", {})["max_utterance_s"] = float(os.environ["VAD_MAX_UTTERANCE_S"])
    if os.environ.get("VOICE_ECHO_TAIL_S"):
        data["echo_tail_s"] = float(os.environ["VOICE_ECHO_TAIL_S"])
    if os.environ.get("LIVEKIT_URL"):
        data.setdefault("livekit", {})["url"] = os.environ["LIVEKIT_URL"]
    if os.environ.get("LIVEKIT_AGENT_NAME"):
        data.setdefault("livekit", {})["agent_name"] = os.environ["LIVEKIT_AGENT_NAME"]
    return VoiceConfig.model_validate(data)


def _safe_config_path(path: str | None) -> Path:
    root = Path.cwd().resolve()
    candidate = Path(path or os.environ.get("AGENT_CONFIG", "config/agent.yaml"))
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    config_root = (root / "config").resolve()
    if candidate != config_root and config_root not in candidate.parents:
        raise HTTPException(
            status_code=400,
            detail="agent config path must be under the config/ directory",
        )
    return candidate


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
