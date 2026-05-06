from __future__ import annotations

from typing import Any


def strip_titles_and_defaults(schema: dict[str, Any]) -> dict[str, Any]:
    """Pydantic emits `title` and pulls definitions into `$defs`. Inline the
    refs and drop fields the LLM doesn't need so the schema stays compact.
    """
    defs = schema.pop("$defs", {})
    return _walk(schema, defs)


def _walk(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        if "$ref" in node:
            ref = node["$ref"].rsplit("/", 1)[-1]
            target = defs.get(ref, {})
            return _walk(target, defs)
        return {
            k: _walk(v, defs)
            for k, v in node.items()
            if k != "title"
        }
    if isinstance(node, list):
        return [_walk(v, defs) for v in node]
    return node
