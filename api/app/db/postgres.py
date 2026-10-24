"""PostgreSQL connection pool (psycopg 3, async).

The pool is module-level so code outside a request (e.g. B's engine) can use it too.
Routes get a connection with `conn: AsyncConnection = Depends(get_conn)`.
"""

from collections.abc import AsyncIterator

from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from app.config import settings

_pool: AsyncConnectionPool | None = None


async def open_pool() -> None:
    global _pool
    _pool = AsyncConnectionPool(settings.database_url, min_size=1, max_size=10, open=False)
    # Doesn't wait for a first connection, so the API still starts if Postgres is down
    await _pool.open(wait=False)


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> AsyncConnectionPool:
    if _pool is None:
        raise RuntimeError("Postgres pool is not open")
    return _pool


async def get_conn() -> AsyncIterator[AsyncConnection]:
    """FastAPI dependency: borrow a connection for the length of one request."""
    async with get_pool().connection() as conn:
        yield conn


async def ping() -> bool:
    try:
        async with get_pool().connection(timeout=2) as conn:
            await conn.execute("SELECT 1")
        return True
    except Exception:
        return False
