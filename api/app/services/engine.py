"""Glue between the API and Person B's engine (engine/scholarql, contract 3).

B's engine is synchronous, so answers are computed in a worker thread. It uses the same
MongoDB vectors and embedding model as /search (app.services.embeddings).
"""

import asyncio

from scholarql import answer as engine_answer
from scholarql.answer import DocumentsUnavailable, EngineError, QueryFailed, UnsupportedQuestion

from app.config import settings
from app.models.ask import Answer
from app.services.embeddings import _embed

__all__ = [
    "DocumentsUnavailable",
    "EngineError",
    "QueryFailed",
    "UnsupportedQuestion",
    "answer",
    "close",
    "configure",
]


def configure() -> None:
    engine_answer.configure(
        database_url=settings.scholarql_database_url or settings.database_url,
        mongodb_uri=settings.mongodb_uri,
        mongodb_db=settings.mongodb_db,
        embed=_embed,
    )


def close() -> None:
    engine_answer.close()


async def answer(question: str) -> Answer:
    result = await asyncio.to_thread(engine_answer.answer, question)
    return Answer(**result)
