"""MongoDB client (PyMongo AsyncMongoClient; Motor is deprecated).

The client connects lazily on first use and manages its own connection pool.
Routes get the database with `db: AsyncDatabase = Depends(get_db)`.
"""

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.config import settings

_client: AsyncMongoClient | None = None


def connect() -> None:
    global _client
    _client = AsyncMongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=3000, tz_aware=True)


async def close() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


def get_client() -> AsyncMongoClient:
    if _client is None:
        raise RuntimeError("Mongo client is not connected")
    return _client


def get_db() -> AsyncDatabase:
    return get_client()[settings.mongodb_db]


async def ping() -> bool:
    try:
        await get_client().admin.command("ping")
        return True
    except Exception:
        return False
