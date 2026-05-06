from __future__ import annotations

from types import SimpleNamespace

from agent.providers.gemini import _is_thought_part, _thinking_config


def test_is_thought_part_only_matches_true_flag() -> None:
    assert _is_thought_part(SimpleNamespace(thought=True))
    assert not _is_thought_part(SimpleNamespace(thought=False))
    assert not _is_thought_part(SimpleNamespace(thought=None))
    assert not _is_thought_part(SimpleNamespace(text="hello"))


def test_gemma_4_disabled_thinking_uses_minimal_level() -> None:
    config = _thinking_config(_capture_kwargs, model="gemma-4-31b-it", enabled=False)

    assert config == {"include_thoughts": False, "thinking_level": "minimal"}


def test_gemini_25_disabled_thinking_uses_zero_budget() -> None:
    config = _thinking_config(_capture_kwargs, model="gemini-2.5-flash", enabled=False)

    assert config == {"include_thoughts": False, "thinking_budget": 0}


def _capture_kwargs(**kwargs):
    return kwargs
