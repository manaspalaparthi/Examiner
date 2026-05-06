from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from .db.repo import TraceRepo

log = logging.getLogger(__name__)


class TraceLogger:
    """Records turn lifecycle events into the `traces` table.

    `span(event)` returns a context manager that records start + end with
    elapsed latency. For point-in-time events use `event(name)`.
    """

    def __init__(self, repo: TraceRepo, conversation_id: UUID, *, enabled: bool = True) -> None:
        self._repo = repo
        self._conv = conversation_id
        self._enabled = enabled
        self._t0 = time.monotonic()

    @property
    def total_ms(self) -> int:
        return int((time.monotonic() - self._t0) * 1000)

    async def event(
        self,
        name: str,
        *,
        message_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self._enabled:
            return
        try:
            await self._repo.record(
                conversation_id=self._conv,
                event=name,
                message_id=message_id,
                metadata=metadata,
            )
        except Exception:
            log.exception("trace: failed to record event %s", name)

    async def span(
        self,
        name: str,
        *,
        latency_ms: int,
        message_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self._enabled:
            return
        try:
            await self._repo.record(
                conversation_id=self._conv,
                event=name,
                message_id=message_id,
                latency_ms=latency_ms,
                metadata=metadata,
            )
        except Exception:
            log.exception("trace: failed to record span %s", name)
