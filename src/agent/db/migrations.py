from __future__ import annotations

import argparse
import logging
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_DIR = Path("supabase/migrations")


async def apply_pending(*args, directory: Path = DEFAULT_DIR, **kwargs) -> list[str]:
    """No-op compatibility hook.

    Supabase migrations are applied by the local Docker init mount on fresh
    volumes and by `supabase db push`/SQL deployment for Cloud. The app no
    longer applies raw SQL at startup because persistence goes through the
    Supabase API layer instead of a direct asyncpg connection.
    """
    _ = (args, kwargs, directory)
    log.info("migrations: managed by Supabase; startup migration hook skipped")
    return []


async def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default=str(DEFAULT_DIR))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    await apply_pending(directory=Path(args.dir))


if __name__ == "__main__":
    import asyncio

    asyncio.run(_main())
