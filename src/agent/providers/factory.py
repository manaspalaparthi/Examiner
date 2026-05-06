from __future__ import annotations

from ..errors import ConfigError
from .base import LLMClient


def make_provider(name: str) -> LLMClient:
    if name == "ollama":
        from .ollama import OllamaClient
        return OllamaClient()
    if name == "gemini":
        from .gemini import GeminiClient
        return GeminiClient()
    raise ConfigError(f"unknown provider: {name!r}")
