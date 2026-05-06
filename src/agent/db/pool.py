from __future__ import annotations

import os

import asyncpg


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url


async def create_pool(
    url: str | None = None,
    *,
    min_size: int = 1,
    max_size: int = 10,
) -> asyncpg.Pool:
    return await asyncpg.create_pool(
        url or database_url(),
        min_size=min_size,
        max_size=max_size,
    )
