from __future__ import annotations

from voice.agent_registry import build_agent
from voice.agent_runtime import RuntimeAgent


def test_runtime_agent_registry_uses_importable_package_path() -> None:
    agent = build_agent("runtime", {"greeting": None})

    assert isinstance(agent, RuntimeAgent)
