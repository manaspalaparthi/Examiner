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

import asyncpg
import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from agent.config import AckConfig, AgentConfig, TimeoutsConfig, TracingConfig, load_agent_config
from agent.db.migrations import apply_pending
from agent.db.pool import create_pool
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


class VADConfig(BaseModel):
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    min_silence_ms: int = Field(default=500, ge=0)
    speech_pad_ms: int = Field(default=200, ge=0)
    max_utterance_s: float = Field(default=30.0, gt=0)


class BargeInConfig(BaseModel):
    enabled: bool = True
    min_speech_ms: int = Field(default=420, ge=0)
    min_rms: float = Field(default=0.012, ge=0.0, le=1.0)


class STTConfig(BaseModel):
    model_id: str | None = None


class TTSConfig(BaseModel):
    model_path: str = "kokoro-v1.0.onnx"
    voices_path: str = "voices-v1.0.bin"
    voice: str = "af_heart"
    speed: float = Field(default=1.0, gt=0.25, le=4.0)
    lang: str = "en-us"


class VoiceConfig(BaseModel):
    vad: VADConfig = Field(default_factory=VADConfig)
    barge_in: BargeInConfig = Field(default_factory=BargeInConfig)
    stt: STTConfig = Field(default_factory=STTConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    echo_tail_s: float = Field(default=0.7, ge=0.0, le=5.0)


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
_db_pool: asyncpg.Pool | None = None


def _cors_origins_from_env() -> list[str]:
    raw = os.environ.get(
        "VOICE_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001",
    )
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db_pool, _default_voice_config
    load_dotenv()
    logging.basicConfig(
        level=os.environ.get("VOICE_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _default_voice_config = _voice_config_from_env()
    if os.environ.get("DATABASE_URL"):
        try:
            _db_pool = await create_pool()
            await apply_pending(_db_pool)
            await _ensure_default_agent_record()
            log.info("database ready")
        except Exception as e:
            _db_pool = None
            log.warning("database unavailable; agent CRUD endpoints will return 503: %s", e)
    if _env_bool("VOICE_PRELOAD_MODELS", default=False):
        log.info("loading default STT and TTS models; first call may take a while")
        await _resources.get_stt(_default_voice_config.stt)
        await _resources.get_tts(_default_voice_config.tts)
        log.info("default voice models loaded")
    try:
        yield
    finally:
        if _db_pool is not None:
            await _db_pool.close()
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
    pool = _require_db()
    rows = await pool.fetch(
        """
        SELECT * FROM agents
        ORDER BY
          CASE status
            WHEN 'active' THEN 0
            WHEN 'draft' THEN 1
            ELSE 2
          END,
          updated_at DESC,
          name ASC
        """
    )
    return [_agent_from_row(row) for row in rows]


@app.post("/api/agents", response_model=AgentRecord, status_code=201)
async def create_agent(request: AgentCreateRequest) -> AgentRecord:
    pool = _require_db()
    if not request.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    agent_id = request.id or _slugify_agent_id(request.name)
    provider = request.provider or _infer_provider(request.model)
    model = request.model or os.environ.get("MODEL_NAME") or "gemma-4-31b-it"
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
    try:
        row = await pool.fetchrow(
            """
            INSERT INTO agents (
              id, user_id, name, description, status, backend_agent, config_path, voice_id,
              provider, model, system_prompt, temperature, max_tokens, history_limit,
              tools, tool_groups, ack, mcp_servers, timeouts, tracing, voice_config,
              agent_config, start_params, metadata
            )
            VALUES (
              $1, $2, $3, $4, $5, $6, $7, $8,
              $9, $10, $11, $12, $13, $14,
              $15, $16, $17::jsonb, $18::jsonb, $19::jsonb, $20::jsonb, $21::jsonb,
              $22::jsonb, $23::jsonb, $24::jsonb
            )
            RETURNING *
            """,
            agent_id,
            request.user_id,
            request.name.strip(),
            request.description,
            request.status,
            request.backend_agent,
            request.config_path,
            request.voice_id,
            provider,
            model,
            request.system_prompt,
            request.temperature,
            request.max_tokens,
            request.history_limit,
            request.tools,
            request.tool_groups,
            _dump_jsonb(ack),
            _dump_jsonb(request.mcp_servers),
            _dump_jsonb(timeouts),
            _dump_jsonb(tracing),
            _dump_jsonb(voice_config),
            _dump_jsonb(agent_config),
            _dump_jsonb(request.start_params),
            _dump_jsonb(request.metadata),
        )
    except asyncpg.UniqueViolationError as e:
        raise HTTPException(status_code=409, detail=f"Agent {agent_id!r} already exists") from e
    return _agent_from_row(row)


@app.get("/api/agents/{agent_id}", response_model=AgentRecord)
async def get_agent(agent_id: str) -> AgentRecord:
    pool = _require_db()
    row = await pool.fetchrow("SELECT * FROM agents WHERE id = $1", agent_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _agent_from_row(row)


@app.post("/api/agents/{agent_id}/chat", response_model=AgentChatResponse)
async def chat_with_agent(agent_id: str, request: AgentChatRequest) -> AgentChatResponse:
    pool = _require_db()
    row = await pool.fetchrow("SELECT * FROM agents WHERE id = $1", agent_id)
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
    row = await pool.fetchrow("SELECT * FROM agents WHERE id = $1", agent_id)
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
    pool = _require_db()
    current = await pool.fetchrow("SELECT * FROM agents WHERE id = $1", agent_id)
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

    row = await pool.fetchrow(
        """
        UPDATE agents SET
          name = $2,
          user_id = $3,
          description = $4,
          status = $5,
          backend_agent = $6,
          config_path = $7,
          voice_id = $8,
          provider = $9,
          model = $10,
          system_prompt = $11,
          temperature = $12,
          max_tokens = $13,
          history_limit = $14,
          tools = $15,
          tool_groups = $16,
          ack = $17::jsonb,
          mcp_servers = $18::jsonb,
          timeouts = $19::jsonb,
          tracing = $20::jsonb,
          voice_config = $21::jsonb,
          agent_config = $22::jsonb,
          start_params = $23::jsonb,
          metadata = $24::jsonb
        WHERE id = $1
        RETURNING *
        """,
        agent_id,
        update.get("name", current_agent.name),
        update.get("user_id", current_agent.user_id),
        update.get("description", current_agent.description),
        update.get("status", current_agent.status),
        update.get("backend_agent", current_agent.backend_agent),
        update.get("config_path", current_agent.config_path),
        update.get("voice_id", current_agent.voice_id),
        provider,
        model,
        system_prompt,
        temperature,
        max_tokens,
        history_limit,
        update.get("tools", current_agent.tools),
        tool_groups,
        _dump_jsonb(ack),
        _dump_jsonb(mcp_servers),
        _dump_jsonb(timeouts),
        _dump_jsonb(tracing),
        _dump_jsonb(update.get("voice_config", current_agent.voice_config)),
        _dump_jsonb(agent_config),
        _dump_jsonb(update.get("start_params", current_agent.start_params)),
        _dump_jsonb(update.get("metadata", current_agent.metadata)),
    )
    return _agent_from_row(row)


@app.delete("/api/agents/{agent_id}", status_code=204)
async def delete_agent(agent_id: str) -> None:
    pool = _require_db()
    result = await pool.execute("DELETE FROM agents WHERE id = $1", agent_id)
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Agent not found")


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


def _require_db() -> asyncpg.Pool:
    if _db_pool is None:
        raise HTTPException(
            status_code=503,
            detail="Database is not available. Set DATABASE_URL and start Postgres.",
        )
    return _db_pool


async def _ensure_default_agent_record() -> None:
    if _db_pool is None:
        return
    existing = await _db_pool.fetchval("SELECT COUNT(*) FROM agents")
    if existing:
        return
    config_path = os.environ.get("AGENT_CONFIG", "config/agent.yaml")
    try:
        cfg = load_agent_config(config_path)
    except ConfigError as e:
        log.warning("skipping default agent seed: %s", e)
        return
    voice_config = _default_voice_config.model_dump(mode="json")
    await _db_pool.execute(
        """
        INSERT INTO agents (
          id, user_id, name, description, status, backend_agent, config_path, voice_id,
          provider, model, system_prompt, temperature, max_tokens, history_limit,
          tools, tool_groups, ack, mcp_servers, timeouts, tracing, voice_config,
          agent_config, start_params, metadata
        )
        VALUES (
          $1, 'admin', $2, $3, 'active', 'runtime', $4, $5,
          $6, $7, $8, $9, $10, $11,
          ARRAY[]::TEXT[], $12, $13::jsonb, $14::jsonb, $15::jsonb, $16::jsonb, $17::jsonb,
          $18::jsonb, '{}'::jsonb, $19::jsonb
        )
        ON CONFLICT (id) DO NOTHING
        """,
        cfg.agent_id,
        _humanize_agent_id(cfg.agent_id),
        "Runtime voice agent loaded from config/agent.yaml.",
        config_path,
        voice_config["tts"]["voice"],
        cfg.provider,
        cfg.model,
        cfg.system_prompt,
        cfg.temperature,
        cfg.max_tokens,
        cfg.history_limit,
        cfg.tool_groups,
        _dump_jsonb(cfg.ack.model_dump(mode="json")),
        _dump_jsonb([server.model_dump(mode="json") for server in cfg.mcp_servers]),
        _dump_jsonb(cfg.timeouts.model_dump(mode="json")),
        _dump_jsonb(cfg.tracing.model_dump(mode="json")),
        _dump_jsonb(voice_config),
        _dump_jsonb(cfg.model_dump(mode="json")),
        _dump_jsonb({"seeded_from": config_path}),
    )


def _agent_from_row(row: asyncpg.Record) -> AgentRecord:
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
    return VoiceConfig(
        stt=STTConfig(model_id=os.environ.get("PARAKEET_MODEL")),
        tts=TTSConfig(
            model_path=os.environ.get("KOKORO_MODEL", "kokoro-v1.0.onnx"),
            voices_path=os.environ.get("KOKORO_VOICES", "voices-v1.0.bin"),
            voice=os.environ.get("KOKORO_VOICE", "af_heart"),
            speed=float(os.environ.get("KOKORO_SPEED", "1.0")),
            lang=os.environ.get("KOKORO_LANG", "en-us"),
        ),
        vad=VADConfig(
            threshold=float(os.environ.get("VAD_THRESHOLD", "0.5")),
            min_silence_ms=int(os.environ.get("VAD_MIN_SILENCE_MS", "500")),
            speech_pad_ms=int(os.environ.get("VAD_SPEECH_PAD_MS", "200")),
            max_utterance_s=float(os.environ.get("VAD_MAX_UTTERANCE_S", "30.0")),
        ),
        echo_tail_s=float(os.environ.get("VOICE_ECHO_TAIL_S", "0.7")),
    )


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
