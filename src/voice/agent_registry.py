from __future__ import annotations

from importlib import import_module
from typing import Any

from .agent_base import AgentBackend

_REGISTRY: dict[str, type[AgentBackend] | str] = {
    "langgraph": "voice.agent_langgraph:LangGraphAgent",
    "runtime": "voice.agent_runtime:RuntimeAgent",
}


def register(name: str, cls: type[AgentBackend]) -> None:
    _REGISTRY[name] = cls


def registered_agents() -> list[str]:
    return sorted(_REGISTRY)


def build_agent(name: str, config: dict[str, Any] | None = None) -> AgentBackend:
    if name not in _REGISTRY:
        raise ValueError(
            f"Unknown agent backend {name!r}. Registered: {sorted(_REGISTRY)}"
        )
    cls = _resolve(_REGISTRY[name])
    return cls(**(config or {}))


def _resolve(value: type[AgentBackend] | str) -> type[AgentBackend]:
    if isinstance(value, str):
        module_name, _, attr = value.partition(":")
        module = import_module(module_name)
        return getattr(module, attr)
    return value
