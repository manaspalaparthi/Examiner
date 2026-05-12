from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from supabase import Client


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


def _row_to_conv(row: dict[str, Any]) -> Conversation:
    return Conversation(
        id=_uuid(row["id"]),
        agent_id=row["agent_id"],
        user_id=row.get("user_id"),
        system_prompt=row["system_prompt"],
        provider=row["provider"],
        model=row["model"],
        metadata=_load_jsonb(row.get("metadata")) or {},
        created_at=_datetime(row["created_at"]),
        updated_at=_datetime(row["updated_at"]),
    )


def _row_to_msg(row: dict[str, Any]) -> Message:
    return Message(
        id=_uuid(row["id"]),
        conversation_id=_uuid(row["conversation_id"]),
        parent_id=_uuid_or_none(row.get("parent_id")),
        role=row["role"],
        kind=row["kind"],
        content=row.get("content"),
        content_json=_load_jsonb(row.get("content_json")),
        tool_name=row.get("tool_name"),
        tool_call_id=row.get("tool_call_id"),
        latency_ms=row.get("latency_ms"),
        created_at=_datetime(row["created_at"]),
        metadata=_load_jsonb(row.get("metadata")) or {},
    )


def _load_jsonb(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _uuid_or_none(value: Any) -> UUID | None:
    return None if value is None else _uuid(value)


def _datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    raw = str(value).replace("Z", "+00:00")
    return datetime.fromisoformat(raw)


async def _call(fn):
    return await asyncio.to_thread(fn)


def _single(response) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return data[0] if data else None
    return data


class ConversationRepo:
    def __init__(self, client: Client) -> None:
        self._client = client

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
        payload = {
            "agent_id": agent_id,
            "user_id": user_id,
            "system_prompt": system_prompt,
            "provider": provider,
            "model": model,
            "metadata": metadata or {},
        }
        row = _single(await _call(lambda: self._client.table("conversations").insert(payload).execute()))
        if row is None:
            raise RuntimeError("Supabase did not return the created conversation")
        return _row_to_conv(row)

    async def get(self, conversation_id: UUID) -> Conversation | None:
        response = await _call(
            lambda: self._client.table("conversations")
            .select("*")
            .eq("id", str(conversation_id))
            .limit(1)
            .execute()
        )
        row = _single(response)
        return _row_to_conv(row) if row else None

    async def touch(self, conversation_id: UUID) -> None:
        await _call(
            lambda: self._client.table("conversations")
            .update({"updated_at": datetime.now(UTC).isoformat()})
            .eq("id", str(conversation_id))
            .execute()
        )


class MessageRepo:
    def __init__(self, client: Client) -> None:
        self._client = client

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
        payload = {
            "conversation_id": str(conversation_id),
            "parent_id": str(parent_id) if parent_id else None,
            "role": role,
            "kind": kind,
            "content": content,
            "content_json": content_json,
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            "latency_ms": latency_ms,
            "metadata": metadata or {},
        }
        row = _single(await _call(lambda: self._client.table("messages").insert(payload).execute()))
        if row is None:
            raise RuntimeError("Supabase did not return the created message")
        return _row_to_msg(row)

    async def recent(self, conversation_id: UUID, *, limit: int) -> list[Message]:
        response = await _call(
            lambda: self._client.table("messages")
            .select("*")
            .eq("conversation_id", str(conversation_id))
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = getattr(response, "data", None) or []
        return list(reversed([_row_to_msg(r) for r in rows]))


class TraceRepo:
    def __init__(self, client: Client) -> None:
        self._client = client

    async def record(
        self,
        *,
        conversation_id: UUID,
        event: str,
        message_id: UUID | None = None,
        latency_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "conversation_id": str(conversation_id),
            "message_id": str(message_id) if message_id else None,
            "event": event,
            "latency_ms": latency_ms,
            "ended_at": datetime.now(UTC).isoformat() if latency_ms is not None else None,
            "metadata": metadata or {},
        }
        await _call(lambda: self._client.table("traces").insert(payload).execute())


class AgentRepo:
    def __init__(self, client: Client) -> None:
        self._client = client

    async def list(self) -> list[dict[str, Any]]:
        response = await _call(lambda: self._client.table("agents").select("*").execute())
        rows = getattr(response, "data", None) or []
        status_rank = {"active": 0, "draft": 1, "archived": 2}
        return sorted(rows, key=lambda r: (status_rank.get(r.get("status"), 9), r.get("name") or ""))

    async def get(self, agent_id: str) -> dict[str, Any] | None:
        response = await _call(
            lambda: self._client.table("agents").select("*").eq("id", agent_id).limit(1).execute()
        )
        return _single(response)

    async def count(self) -> int:
        response = await _call(
            lambda: self._client.table("agents").select("id", count="exact").limit(1).execute()
        )
        return int(getattr(response, "count", None) or 0)

    async def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = _single(await _call(lambda: self._client.table("agents").insert(payload).execute()))
        if row is None:
            raise RuntimeError("Supabase did not return the created agent")
        return row

    async def update(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        response = await _call(
            lambda: self._client.table("agents").update(payload).eq("id", agent_id).execute()
        )
        return _single(response)

    async def delete(self, agent_id: str) -> bool:
        response = await _call(
            lambda: self._client.table("agents").delete().eq("id", agent_id).execute()
        )
        return bool(getattr(response, "data", None))


class ConversationViewRepo:
    def __init__(self, client: Client) -> None:
        self._client = client

    async def list(self, *, agent_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        query = self._client.table("conversations").select("*, agents(name)")
        if agent_id:
            query = query.eq("agent_id", agent_id)
        response = await _call(lambda: query.order("updated_at", desc=True).execute())
        rows = getattr(response, "data", None) or []
        if status and status != "all":
            rows = [r for r in rows if _conversation_status(r) == status]
        return [_conversation_payload(r, []) for r in rows]

    async def get(self, conversation_id: UUID) -> dict[str, Any] | None:
        conv_response = await _call(
            lambda: self._client.table("conversations")
            .select("*, agents(name)")
            .eq("id", str(conversation_id))
            .limit(1)
            .execute()
        )
        conv = _single(conv_response)
        if conv is None:
            return None
        msg_response = await _call(
            lambda: self._client.table("messages")
            .select("*")
            .eq("conversation_id", str(conversation_id))
            .order("created_at")
            .execute()
        )
        return _conversation_payload(conv, getattr(msg_response, "data", None) or [])


def _conversation_status(row: dict[str, Any]) -> str:
    metadata = _load_jsonb(row.get("metadata")) or {}
    return str(metadata.get("status") or "completed")


def _conversation_payload(row: dict[str, Any], messages: list[dict[str, Any]]) -> dict[str, Any]:
    metadata = _load_jsonb(row.get("metadata")) or {}
    agent = row.get("agents") or {}
    started = row.get("created_at")
    return {
        "id": row["id"],
        "agentId": row["agent_id"],
        "agentName": agent.get("name") or row["agent_id"],
        "callerNumber": metadata.get("caller_number"),
        "startedAt": started,
        "durationSec": int(metadata.get("duration_sec") or 0),
        "status": _conversation_status(row),
        "messages": [
            {
                "id": m["id"],
                "role": "agent" if m.get("role") == "assistant" else m.get("role", "system"),
                "content": m.get("content") or "",
                "timestamp": m.get("created_at"),
            }
            for m in messages
            if m.get("kind") in {"user_text", "assistant_text", "ack", "error"}
        ],
    }
