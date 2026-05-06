from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from .errors import ConfigError


class AckConfig(BaseModel):
    enabled: bool = True
    phrases: list[str] = Field(default_factory=list)


class TimeoutsConfig(BaseModel):
    tool_s: float = 10.0
    mcp_s: float = 10.0
    llm_first_token_s: float = 8.0


class TracingConfig(BaseModel):
    enabled: bool = True


class SubagentsConfig(BaseModel):
    enabled: bool = False
    max_children: int = Field(default=4, ge=1, le=4)
    max_iters: int = Field(default=4, ge=1, le=8)
    timeout_s: float = Field(default=45.0, gt=0)


class MCPServerConfig(BaseModel):
    name: str
    transport: Literal["stdio", "sse"] = "stdio"
    command: list[str] | None = None
    url: str | None = None
    enabled: bool = True
    timeout_s: float = 10.0


class AgentConfig(BaseModel):
    agent_id: str
    system_prompt: str
    provider: Literal["gemini", "ollama"]
    model: str
    temperature: float = 0.3
    max_tokens: int | None = None
    thinking_enabled: bool = True
    history_limit: int = 30
    tool_groups: list[str] = Field(default_factory=list)
    ack: AckConfig = Field(default_factory=AckConfig)
    mcp_servers: list[MCPServerConfig] = Field(default_factory=list)
    subagents: SubagentsConfig = Field(default_factory=SubagentsConfig)
    timeouts: TimeoutsConfig = Field(default_factory=TimeoutsConfig)
    tracing: TracingConfig = Field(default_factory=TracingConfig)


_ENV_OVERRIDES: dict[str, tuple[str, ...]] = {
    "MODEL_PROVIDER": ("provider",),
    "MODEL_NAME": ("model",),
}


def load_agent_config(path: str | Path | None = None) -> AgentConfig:
    """Load agent config from a YAML file, with select env-var overrides."""
    p = Path(path or os.environ.get("AGENT_CONFIG", "config/agent.yaml"))
    if not p.exists():
        raise ConfigError(f"agent config not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}
    for env_key, keypath in _ENV_OVERRIDES.items():
        val = os.environ.get(env_key)
        if not val:
            continue
        cursor = raw
        for k in keypath[:-1]:
            cursor = cursor.setdefault(k, {})
        cursor[keypath[-1]] = val
    try:
        return AgentConfig.model_validate(raw)
    except Exception as e:  # pydantic ValidationError
        raise ConfigError(f"invalid agent config at {p}: {e}") from e
