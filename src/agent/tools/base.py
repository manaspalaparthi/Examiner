from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from ..errors import ToolValidationError
from ..providers.base import ToolSchema
from .schema import strip_titles_and_defaults

ToolHandler = Callable[[Any, "ToolContext"], Awaitable["ToolResult"]]


@dataclass
class ToolContext:
    conversation_id: str
    call_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """Returned by a tool handler. `output` becomes the LLM-facing payload.

    `summary` is a short human-readable line for trace/UI display; if None,
    a truncated `output` is used.
    """

    output: str
    summary: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolSpec:
    """Unified tool spec for both local and MCP-backed tools.

    For local tools, register with a Pydantic `validator` model and the
    handler receives an instance of that model. For MCP/raw tools, omit
    the validator and the handler receives the args dict as-is.
    """

    name: str
    description: str
    handler: ToolHandler
    parameters: dict[str, Any]
    groups: tuple[str, ...] = ()
    server: str | None = None
    validator: type[BaseModel] | None = None
    timeout_s: float | None = None

    def to_provider_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
        )


class ToolRegistry:
    """In-memory tool registry filterable by group tags."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"duplicate tool: {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def for_groups(self, groups: Sequence[str]) -> list[ToolSpec]:
        if not groups:
            return list(self._tools.values())
        wanted = set(groups)
        return [t for t in self._tools.values() if wanted.intersection(t.groups)]

    def all(self) -> list[ToolSpec]:
        return list(self._tools.values())


def tool(
    *,
    name: str,
    description: str,
    schema: type[BaseModel],
    groups: Sequence[str] = (),
    server: str | None = None,
    timeout_s: float | None = None,
) -> Callable[[ToolHandler], ToolSpec]:
    """Decorator: turn an async handler into a `ToolSpec` with Pydantic validation."""

    parameters = strip_titles_and_defaults(schema.model_json_schema())

    def deco(handler: ToolHandler) -> ToolSpec:
        return ToolSpec(
            name=name,
            description=description,
            handler=handler,
            parameters=parameters,
            groups=tuple(groups),
            server=server,
            validator=schema,
            timeout_s=timeout_s,
        )

    return deco


def validate_args(spec: ToolSpec, raw: dict[str, Any]) -> Any:
    """Returns a validated `BaseModel` for local tools, or the raw dict for raw tools."""
    if spec.validator is None:
        return raw
    try:
        return spec.validator.model_validate(raw)
    except ValidationError as e:
        raise ToolValidationError(str(e)) from e
