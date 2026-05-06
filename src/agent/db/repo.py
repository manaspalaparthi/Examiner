from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    import asyncpg


@dataclass
class Conversation:
    id: UUID
    agent_id: str
    user_id: str | None
    system_prompt: str
    provider: str
    model: str
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass
class Message:
    id: UUID
    conversation_id: UUID
    parent_id: UUID | None
    role: str
    kind: str
    content: str | None
    content_json: dict[str, Any] | None
    tool_name: str | None
    tool_call_id: str | None
    latency_ms: int | None
    created_at: datetime
    metadata: dict[str, Any]


@dataclass
class Trace:
    id: UUID
    conversation_id: UUID
    message_id: UUID | None
    event: str
    started_at: datetime
    ended_at: datetime | None
    latency_ms: int | None
    metadata: dict[str, Any]


def _row_to_conv(row: asyncpg.Record) -> Conversation:
    return Conversation(
        id=row["id"],
        agent_id=row["agent_id"],
        user_id=row["user_id"],
        system_prompt=row["system_prompt"],
        provider=row["provider"],
        model=row["model"],
        metadata=_load_jsonb(row["metadata"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_msg(row: asyncpg.Record) -> Message:
    return Message(
        id=row["id"],
        conversation_id=row["conversation_id"],
        parent_id=row["parent_id"],
        role=row["role"],
        kind=row["kind"],
        content=row["content"],
        content_json=_load_jsonb(row["content_json"]),
        tool_name=row["tool_name"],
        tool_call_id=row["tool_call_id"],
        latency_ms=row["latency_ms"],
        created_at=row["created_at"],
        metadata=_load_jsonb(row["metadata"]),
    )


def _load_jsonb(value: Any) -> Any:
    """asyncpg returns jsonb as either str or already-decoded; normalize."""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _dump_jsonb(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value)


class ConversationRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self,
        *,
        agent_id: str,
        system_prompt: str,
        provider: str,
        model: str,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Conversation:
        row = await self._pool.fetchrow(
            """
            INSERT INTO conversations (agent_id, user_id, system_prompt, provider, model, metadata)
            VALUES ($1, $2, $3, $4, $5, COALESCE($6::jsonb, '{}'::jsonb))
            RETURNING *
            """,
            agent_id, user_id, system_prompt, provider, model,
            _dump_jsonb(metadata or {}),
        )
        return _row_to_conv(row)

    async def get(self, conversation_id: UUID) -> Conversation | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM conversations WHERE id = $1", conversation_id
        )
        return _row_to_conv(row) if row else None

    async def touch(self, conversation_id: UUID) -> None:
        await self._pool.execute(
            "UPDATE conversations SET updated_at = NOW() WHERE id = $1",
            conversation_id,
        )


class MessageRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def append(
        self,
        *,
        conversation_id: UUID,
        role: str,
        kind: str,
        content: str | None = None,
        content_json: dict[str, Any] | None = None,
        tool_name: str | None = None,
        tool_call_id: str | None = None,
        parent_id: UUID | None = None,
        latency_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Message:
        row = await self._pool.fetchrow(
            """
            INSERT INTO messages
                (conversation_id, parent_id, role, kind, content, content_json,
                 tool_name, tool_call_id, latency_ms, metadata)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, COALESCE($10::jsonb, '{}'::jsonb))
            RETURNING *
            """,
            conversation_id, parent_id, role, kind, content,
            _dump_jsonb(content_json), tool_name, tool_call_id, latency_ms,
            _dump_jsonb(metadata or {}),
        )
        return _row_to_msg(row)

    async def recent(self, conversation_id: UUID, *, limit: int) -> list[Message]:
        rows = await self._pool.fetch(
            """
            SELECT * FROM messages
            WHERE conversation_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            conversation_id, limit,
        )
        return list(reversed([_row_to_msg(r) for r in rows]))


class TraceRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def record(
        self,
        *,
        conversation_id: UUID,
        event: str,
        message_id: UUID | None = None,
        latency_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO traces (conversation_id, message_id, event, latency_ms, ended_at, metadata)
            VALUES ($1, $2, $3, $4::int,
                    CASE WHEN $4::int IS NULL THEN NULL ELSE NOW() END,
                    COALESCE($5::jsonb, '{}'::jsonb))
            """,
            conversation_id, message_id, event, latency_ms,
            _dump_jsonb(metadata or {}),
        )
