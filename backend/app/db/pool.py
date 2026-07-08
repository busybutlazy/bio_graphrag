"""Shared asyncpg connection pool.

Replaces the per-request ``asyncpg.connect`` calls the DB helpers used to make.
The pool is created lazily on first use and reused for the life of the process,
so request handlers no longer pay a fresh TCP + auth round-trip per query.

asyncpg pools are bound to the event loop they were created on. The app runs a
single loop, but the test suite spins up several (``asyncio.run`` per fixture,
TestClient's own loop), so we key the cached pool by its loop and rebuild if the
running loop changed. In production this branch is taken exactly once.
"""

import asyncio
from contextlib import asynccontextmanager

import asyncpg

from app.core.config import settings

_pool: asyncpg.Pool | None = None
_pool_loop: asyncio.AbstractEventLoop | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool, _pool_loop
    loop = asyncio.get_running_loop()
    if _pool is None or _pool_loop is not loop or _pool.is_closing():
        _pool = await asyncpg.create_pool(
            host=settings.postgres_host,
            port=settings.postgres_port,
            database=settings.postgres_db,
            user=settings.postgres_user,
            password=settings.postgres_password,
            min_size=1,
            max_size=10,
        )
        _pool_loop = loop
    return _pool


@asynccontextmanager
async def connection():
    """Acquire a pooled connection: ``async with connection() as conn: ...``."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn
