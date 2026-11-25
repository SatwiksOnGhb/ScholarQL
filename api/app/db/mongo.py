"""MongoDB client (PyMongo AsyncMongoClient; Motor is deprecated).

The client connects lazily on first use and manages its own connection pool.
Routes get the database with `db: AsyncDatabase = Depends(get_db)`.
"""

from bson.binary import Binary
from bson.codec_options import TypeDecoder, TypeRegistry
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.config import settings

_client: AsyncMongoClient | None = None


class _PackedVectorDecoder(TypeDecoder):
    """Atlas stores embeddings as packed float32 BSON vectors (binData subtype 9) to fit the
    free tier; decode them to plain lists so the code sees the same shape as locally."""

    bson_type = Binary

    def transform_bson(self, value: Binary):
        return value.as_vector().data if value.subtype == 9 else value


TYPE_REGISTRY = TypeRegistry([_PackedVectorDecoder()])


def connect() -> None:
    global _client
    _client = AsyncMongoClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=3000,
        tz_aware=True,
        type_registry=TYPE_REGISTRY,
    )


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
