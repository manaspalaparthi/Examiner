from __future__ import annotations

import logging
import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

from ..errors import ProviderError
from .base import (
    LLMClient,
    LLMError,
    LLMFinish,
    LLMThinkingDelta,
    LLMTextDelta,
    LLMToolCall,
    ProviderEvent,
    ProviderMessage,
    ToolSchema,
)

log = logging.getLogger(__name__)


class GeminiClient(LLMClient):
    """Streams from Gemini via google-genai.

    Gemini emits function calls as a single `Part` (no partial JSON), so
    tool-call args are forwarded to the runtime atomically. Text parts
    arrive incrementally as `LLMTextDelta`s.
    """

    def __init__(self, api_key: str | None = None) -> None:
        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError as e:
            raise ProviderError("google-genai not installed") from e
        key = api_key or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise ProviderError("GOOGLE_API_KEY is not set")
        self._client = genai.Client(api_key=key)
        self._types = genai_types

    async def aclose(self) -> None:
        return None

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
        types = self._types
        config_kwargs: dict[str, Any] = {
            "temperature": temperature,
            "system_instruction": system or None,
            "automatic_function_calling": types.AutomaticFunctionCallingConfig(
                disable=True
            ),
        }
        if max_tokens is not None:
            config_kwargs["max_output_tokens"] = max_tokens
        if tools:
            config_kwargs["tools"] = [
                types.Tool(function_declarations=[_to_gemini_fn(t) for t in tools])
            ]
        thinking_config = getattr(types, "ThinkingConfig", None)
        if thinking_config is not None:
            config_kwargs["thinking_config"] = _thinking_config(
                thinking_config,
                model=model,
                enabled=thinking_enabled,
            )

        contents = _to_gemini_contents(messages)
        response = await self._open_stream(
            model=model,
            contents=contents,
            config_kwargs=config_kwargs,
            thinking_enabled=thinking_enabled,
        )

        any_tool_call = False
        try:
            async for chunk in response:
                cands = getattr(chunk, "candidates", None) or []
                if not cands:
                    continue
                cand = cands[0]
                content = getattr(cand, "content", None)
                parts = getattr(content, "parts", None) or []
                for part in parts:
                    text = getattr(part, "text", "") or ""
                    if _is_thought_part(part):
                        if text and thinking_enabled:
                            yield LLMThinkingDelta(text=text)
                        continue
                    if text:
                        yield LLMTextDelta(text=text)
                    fc = getattr(part, "function_call", None)
                    if fc and getattr(fc, "name", ""):
                        any_tool_call = True
                        args = _coerce_args(getattr(fc, "args", {}) or {})
                        yield LLMToolCall(
                            call_id=f"call_{uuid.uuid4().hex[:12]}",
                            name=fc.name,
                            args=args,
                        )
        except Exception as e:
            yield LLMError(f"gemini stream error: {e}")
            yield LLMFinish(reason="error")
            return

        yield LLMFinish(reason="tool_calls" if any_tool_call else "stop")

    async def _open_stream(
        self,
        *,
        model: str,
        contents: list[dict[str, Any]],
        config_kwargs: dict[str, Any],
        thinking_enabled: bool,
    ) -> Any:
        types = self._types
        try:
            return await self._client.aio.models.generate_content_stream(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(**config_kwargs),
            )
        except Exception as e:
            retry_config = dict(config_kwargs)
            if "thinking_config" in retry_config and _is_unsupported_thinking_error(e):
                retry_config.pop("thinking_config", None)
                try:
                    return await self._client.aio.models.generate_content_stream(
                        model=model,
                        contents=contents,
                        config=types.GenerateContentConfig(**retry_config),
                    )
                except Exception as retry_e:
                    e = retry_e

            fallback = _fallback_model(model)
            if fallback:
                log.warning("gemini model %s failed; retrying with %s: %s", model, fallback, e)
                fallback_config = dict(retry_config)
                thinking_config = getattr(types, "ThinkingConfig", None)
                if thinking_config is not None and "thinking_config" in config_kwargs:
                    fallback_config["thinking_config"] = _thinking_config(
                        thinking_config,
                        model=fallback,
                        enabled=thinking_enabled,
                    )
                try:
                    return await self._client.aio.models.generate_content_stream(
                        model=fallback,
                        contents=contents,
                        config=types.GenerateContentConfig(**fallback_config),
                    )
                except Exception as fallback_e:
                    raise ProviderError(
                        f"gemini request failed on {model} and fallback {fallback}: {fallback_e}"
                    ) from fallback_e
            raise ProviderError(f"gemini request failed: {e}") from e


def _is_thought_part(part: Any) -> bool:
    """Gemini marks non-user-facing reasoning parts with ``thought=True``."""
    return getattr(part, "thought", None) is True


def _thinking_config(thinking_config: Any, *, model: str, enabled: bool) -> Any:
    if enabled:
        return thinking_config(include_thoughts=True)
    if _uses_thinking_level(model):
        return _first_supported_thinking_config(
            thinking_config,
            [
                {"include_thoughts": False, "thinking_level": "minimal"},
                {"thinking_level": "minimal"},
                {"include_thoughts": False},
            ],
        )
    return _first_supported_thinking_config(
        thinking_config,
        [
            {"include_thoughts": False, "thinking_budget": 0},
            {"include_thoughts": False},
        ],
    )


def _uses_thinking_level(model: str) -> bool:
    normalized = model.lower()
    return normalized.startswith(("gemini-3", "gemma-4"))


def _fallback_model(model: str) -> str | None:
    configured = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash").strip()
    if not configured:
        return None
    if model == configured:
        return None
    if model.lower() == "gemma-4-31b-it":
        return configured
    return None


def _first_supported_thinking_config(thinking_config: Any, attempts: list[dict[str, Any]]) -> Any:
    last_error: TypeError | None = None
    for kwargs in attempts:
        try:
            return thinking_config(**kwargs)
        except TypeError as e:
            last_error = e
    try:
        return thinking_config()
    except TypeError:
        if last_error is not None:
            raise last_error
        raise


def _is_unsupported_thinking_error(error: Exception) -> bool:
    message = str(error).lower()
    return "thinking" in message or "thought" in message


def _to_gemini_contents(messages: list[ProviderMessage]) -> list[dict[str, Any]]:
    contents: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "system":
            continue  # system_instruction is set separately
        if m.role == "tool":
            contents.append({
                "role": "user",
                "parts": [{
                    "function_response": {
                        "name": m.tool_call_id or "tool",
                        "response": _wrap_tool_response(m.content or ""),
                    }
                }],
            })
            continue
        gem_role = "user" if m.role == "user" else "model"
        parts: list[dict[str, Any]] = []
        if m.content:
            parts.append({"text": m.content})
        for tc in m.tool_calls:
            parts.append({"function_call": {"name": tc.name, "args": tc.args}})
        if not parts:
            parts.append({"text": ""})
        contents.append({"role": gem_role, "parts": parts})
    return contents


def _to_gemini_fn(t: ToolSchema) -> dict[str, Any]:
    return {
        "name": t.name,
        "description": t.description,
        "parameters": t.parameters,
    }


def _wrap_tool_response(content: str) -> dict[str, Any]:
    """Gemini expects a dict for function_response; wrap raw strings."""
    return {"result": content}


def _coerce_args(args: Any) -> dict[str, Any]:
    """Gemini's args may be a proto MapComposite or plain dict; normalize."""
    if isinstance(args, dict):
        return dict(args)
    try:
        return dict(args)
    except Exception:
        return {"_raw": str(args)}
