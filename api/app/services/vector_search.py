"""Semantic search over MongoDB paper_content with Atlas Vector Search.

`vector_search(text, k, filters)` is contract 4: B's hybrid router calls it to get candidate
paper IDs, then filters them in SQL. `search_papers` builds the /search response on top.
"""

import logging
from typing import TypedDict

from pymongo.errors import PyMongoError

from app.db import mongo
from app.errors import ApiError
from app.models.search import SearchHit
from app.services.embeddings import embed_query
from app.services.paper_lookup import paper_summaries

log = logging.getLogger(__name__)

INDEX = "paper_embedding"  # defined in mongo/vector-indexes.json
SNIPPET_CHARS = 400


class VectorFilters(TypedDict, total=False):
    """All optional. Each one must be a `filter` field in the vector index."""

    year_from: int
    year_to: int
    venue_id: str


def mongo_filter(filters: VectorFilters | None) -> dict | None:
    """Translate VectorFilters into a $vectorSearch pre-filter (applied before ranking)."""
    if not filters:
        return None
    clauses: list[dict] = []
    year: dict = {}
    if filters.get("year_from") is not None:
        year["$gte"] = filters["year_from"]
    if filters.get("year_to") is not None:
        year["$lte"] = filters["year_to"]
    if year:
        clauses.append({"year": year})
    if filters.get("venue_id") is not None:
        clauses.append({"venue_id": {"$eq": filters["venue_id"]}})
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


async def vector_search(
    text: str, k: int = 10, filters: VectorFilters | None = None
) -> list[tuple[str, float]]:
    """Top-k papers by meaning: [(paper_id, score)], best first. Score is cosine-based, 0..1."""
    stage: dict = {
        "index": INDEX,
        "path": "embedding",
        "queryVector": await embed_query(text),
        # More candidates = better recall, slower; ~20x k is the usual starting point
        "numCandidates": min(max(k * 20, 100), 10_000),
        "limit": k,
    }
    if (pre_filter := mongo_filter(filters)) is not None:
        stage["filter"] = pre_filter
    pipeline = [{"$vectorSearch": stage}, {"$project": {"score": {"$meta": "vectorSearchScore"}}}]
    try:
        cursor = await mongo.get_db().paper_content.aggregate(pipeline)
        return [(doc["_id"], doc["score"]) async for doc in cursor]
    except PyMongoError as exc:
        log.warning("vector search failed: %s", exc)
        raise ApiError(503, "service_unavailable", "Search is unavailable right now") from exc


async def search_papers(text: str, k: int, filters: VectorFilters | None) -> list[SearchHit]:
    hits = await vector_search(text, k, filters)
    ids = [paper_id for paper_id, _ in hits]
    if not ids:
        return []

    try:
        cursor = mongo.get_db().paper_content.find(
            {"_id": {"$in": ids}}, {"abstract": 1, "tldr": 1, "year": 1, "venue_id": 1}
        )
        content = {doc["_id"]: doc async for doc in cursor}
    except PyMongoError as exc:
        raise ApiError(503, "service_unavailable", "Search is unavailable right now") from exc
    summaries = await paper_summaries(ids)

    results = []
    for paper_id, score in hits:
        doc = content.get(paper_id, {})
        summary = summaries.get(paper_id)
        abstract = doc.get("abstract") or ""
        results.append(
            SearchHit(
                paper_id=paper_id,
                score=round(score, 4),
                title=summary.title if summary else f"Paper {paper_id}",
                year=doc.get("year"),
                venue_id=doc.get("venue_id"),
                venue_name=summary.venue_name if summary else None,
                tldr=doc.get("tldr"),
                abstract=abstract[:SNIPPET_CHARS] + ("…" if len(abstract) > SNIPPET_CHARS else ""),
            )
        )
    return results
