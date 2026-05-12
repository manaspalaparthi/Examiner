from __future__ import annotations

import os
from typing import Any

from supabase import Client, create_client


def supabase_url() -> str:
    url = os.environ.get("SUPABASE_URL")
    if not url:
        raise RuntimeError("SUPABASE_URL is not set")
    return url


def supabase_service_key() -> str:
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is not set")
    return key


async def create_pool(
    url: str | None = None,
    *,
    min_size: int = 1,
    max_size: int = 10,
) -> Client:
    """Compatibility factory for the old asyncpg pool call sites.

    The runtime now persists through Supabase's Python SDK using the backend-only
    service role key. The old pool sizing arguments are accepted so voice
    backends can migrate without changing their construction path.
    """
    _ = (min_size, max_size)
    return create_client(url or supabase_url(), supabase_service_key())


async def close_pool(client: Any) -> None:
    close = getattr(client, "aclose", None) or getattr(client, "close", None)
    if close is None:
        return
    result = close()
    if hasattr(result, "__await__"):
        await result
