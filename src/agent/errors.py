from __future__ import annotations


class AgentError(Exception):
    """Base for all agent runtime errors."""


class ProviderError(AgentError):
    """LLM provider failed (timeout, API error, malformed stream)."""


class ToolError(AgentError):
    """A registered tool's handler raised."""


class ToolValidationError(ToolError):
    """LLM-supplied tool args failed schema validation."""


class MCPError(AgentError):
    """MCP server connection or call failure."""


class ConfigError(AgentError):
    """Agent configuration is missing or invalid."""
