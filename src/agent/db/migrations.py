from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

import asyncpg

from .pool import create_pool

log = logging.getLogger(__name__)

DEFAULT_DIR = Path("db/migrations")

_TRACK_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS _migrations (
    name TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""


async def apply_pending(pool: asyncpg.Pool, directory: Path = DEFAULT_DIR) -> list[str]:
    """Apply all *.sql files in `directory` not yet recorded in `_migrations`.

    Returns the list of file names that were applied this run.
    """
    files = sorted(p for p in directory.glob("*.sql"))
    if not files:
        log.info("migrations: no files in %s", directory)
        return []
    applied: list[str] = []
    async with pool.acquire() as conn:
        await conn.execute(_TRACK_TABLE_DDL)
        seen = {r["name"] for r in await conn.fetch("SELECT name FROM _migrations")}
        for f in files:
            if f.name in seen:
                continue
            sql = f.read_text(encoding="utf-8")
            log.info("migrations: applying %s", f.name)
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO _migrations (name) VALUES ($1)", f.name
                )
            applied.append(f.name)
    return applied


async def _main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default=str(DEFAULT_DIR))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    pool = await create_pool()
    try:
        applied = await apply_pending(pool, Path(args.dir))
        if applied:
            log.info("migrations: applied %d file(s): %s", len(applied), ", ".join(applied))
        else:
            log.info("migrations: nothing to apply")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(_main())
