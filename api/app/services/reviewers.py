"""Reviewer finder: rank authors by how close their profile is to an abstract, minus conflicts.

Conflicts of interest: the submitting authors, their co-authors, and anyone at a submitting
author's institution. Institutions are excluded inside the vector search (a pre-filter), so a
big lab can't crowd out the results; blocked authors are dropped from an over-fetched list.
"""

import logging
import re
from dataclasses import dataclass

import numpy as np
from pymongo.errors import PyMongoError

from app.db import mongo
from app.errors import ApiError
from app.models.reviewers import (
    AuthorOption,
    ExcludedAuthor,
    ExcludedInstitution,
    MatchingPaper,
    Reviewer,
    ReviewerResponse,
)
from app.services.embeddings import embed_query
from app.services.paper_lookup import institution_names, paper_summaries

log = logging.getLogger(__name__)

INDEX = "author_embedding"  # defined in mongo/vector-indexes.json
MATCHING_PAPERS = 3


async def coauthors(author_id: int) -> set[int]:
    """FAKE stub: authors who share a paper with `author_id`.

    TODO(A): replace with A's SQL function, e.g.
        SELECT coauthor_id FROM coauthors(%s)
    For now it's derived from author_profiles.paper_ids in MongoDB (sample data).
    """
    db = mongo.get_db()
    me = await db.author_profiles.find_one({"_id": author_id}, {"paper_ids": 1})
    if not me:
        return set()
    cursor = db.author_profiles.find(
        {"paper_ids": {"$in": me["paper_ids"]}, "_id": {"$ne": author_id}}, {"_id": 1}
    )
    return {doc["_id"] async for doc in cursor}


@dataclass
class Candidate:
    author_id: int
    name: str
    institution_id: int | None
    paper_ids: list[int]
    score: float


def select_candidates(candidates: list[Candidate], blocked: set[int], k: int) -> list[Candidate]:
    """Best-first candidates minus blocked authors, at most k."""
    return [c for c in candidates if c.author_id not in blocked][:k]


def rank_papers(
    query: np.ndarray, paper_vectors: dict[int, np.ndarray], paper_ids: list[int], n: int
) -> list[tuple[int, float]]:
    """An author's n papers closest to the query, as (paper_id, score) on the same 0..1 scale
    as Atlas's cosine vectorSearchScore: (1 + cosine) / 2. Vectors are unit length."""
    scored = [
        (pid, float((1 + query @ paper_vectors[pid]) / 2))
        for pid in paper_ids
        if pid in paper_vectors
    ]
    return sorted(scored, key=lambda s: s[1], reverse=True)[:n]


async def find_reviewers(abstract: str, author_ids: list[int], k: int) -> ReviewerResponse:
    try:
        return await _find_reviewers(abstract, author_ids, k)
    except PyMongoError as exc:
        log.warning("reviewer search failed: %s", exc)
        raise ApiError(503, "service_unavailable", "Reviewer search is unavailable") from exc


async def _find_reviewers(abstract: str, author_ids: list[int], k: int) -> ReviewerResponse:
    db = mongo.get_db()
    submitted = list(dict.fromkeys(author_ids))  # dedupe, keep order

    # 1. Conflicts of interest
    profiles = {
        d["_id"]: d
        async for d in db.author_profiles.find(
            {"_id": {"$in": submitted}}, {"name": 1, "institution_id": 1}
        )
    }
    coauthor_ids: set[int] = set()
    for author_id in submitted:
        coauthor_ids |= await coauthors(author_id)
    coauthor_ids -= set(submitted)
    blocked = set(submitted) | coauthor_ids
    blocked_institutions = sorted(
        {p["institution_id"] for p in profiles.values() if p.get("institution_id") is not None}
    )

    # 2. Vector search over author profiles, over-fetching to cover blocked authors
    query = await embed_query(abstract)
    limit = min(k + len(blocked), 1000)
    stage: dict = {
        "index": INDEX,
        "path": "embedding",
        "queryVector": query,
        "numCandidates": min(max(limit * 10, 200), 10_000),
        "limit": limit,
    }
    if blocked_institutions:
        stage["filter"] = {"institution_id": {"$nin": blocked_institutions}}
    pipeline = [
        {"$vectorSearch": stage},
        {
            "$project": {
                "name": 1,
                "institution_id": 1,
                "paper_ids": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]
    cursor = await db.author_profiles.aggregate(pipeline)
    candidates = [
        Candidate(d["_id"], d["name"], d.get("institution_id"), d["paper_ids"], d["score"])
        async for d in cursor
    ]
    chosen = select_candidates(candidates, blocked, k)

    # 3. Explain each suggestion with their papers closest to the abstract
    paper_ids = list({pid for c in chosen for pid in c.paper_ids})
    paper_vectors: dict[int, np.ndarray] = {}
    years: dict[int, int | None] = {}
    async for d in db.paper_content.find({"_id": {"$in": paper_ids}}, {"embedding": 1, "year": 1}):
        years[d["_id"]] = d.get("year")
        if "embedding" in d:
            paper_vectors[d["_id"]] = np.asarray(d["embedding"], dtype=np.float32)
    query_vec = np.asarray(query, dtype=np.float32)
    ranked = {
        c.author_id: rank_papers(query_vec, paper_vectors, c.paper_ids, MATCHING_PAPERS)
        for c in chosen
    }
    titles = await paper_summaries([pid for r in ranked.values() for pid, _ in r])
    inst_ids = {c.institution_id for c in chosen if c.institution_id} | set(blocked_institutions)
    inst_names = await institution_names(list(inst_ids))

    # Names for the excluded list: submitting authors from their profiles, co-authors looked up
    names = {d["_id"]: d["name"] for d in profiles.values()}
    if coauthor_ids:
        async for d in db.author_profiles.find({"_id": {"$in": list(coauthor_ids)}}, {"name": 1}):
            names[d["_id"]] = d["name"]

    reviewers = [
        Reviewer(
            author_id=c.author_id,
            name=c.name,
            institution_id=c.institution_id,
            institution_name=inst_names.get(c.institution_id) if c.institution_id else None,
            score=round(c.score, 4),
            paper_count=len(c.paper_ids),
            matching_papers=[
                MatchingPaper(
                    paper_id=pid,
                    title=titles[pid].title if pid in titles else f"Paper W{pid}",
                    year=years.get(pid),
                    score=round(score, 4),
                )
                for pid, score in ranked[c.author_id]
            ],
        )
        for c in chosen
    ]
    excluded = [
        ExcludedAuthor(author_id=a, name=names.get(a), reason="submitting_author")
        for a in submitted
    ] + [
        ExcludedAuthor(author_id=a, name=names.get(a), reason="coauthor")
        for a in sorted(coauthor_ids, key=lambda a: names.get(a) or "")
    ]
    return ReviewerResponse(
        reviewers=reviewers,
        excluded_authors=excluded,
        excluded_institutions=[
            ExcludedInstitution(institution_id=i, name=inst_names.get(i))
            for i in blocked_institutions
        ],
    )


async def search_authors(q: str, limit: int) -> list[AuthorOption]:
    """Authors whose name contains `q` (case-insensitive), most papers first.

    TODO(A): could use A's pg_trgm fuzzy match on the author table instead.
    """
    pipeline = [
        {"$match": {"name": {"$regex": re.escape(q), "$options": "i"}}},
        {"$project": {"name": 1, "institution_id": 1, "n": {"$size": "$paper_ids"}}},
        {"$sort": {"n": -1, "name": 1}},
        {"$limit": limit},
    ]
    try:
        cursor = await mongo.get_db().author_profiles.aggregate(pipeline)
        docs = [d async for d in cursor]
    except PyMongoError as exc:
        raise ApiError(503, "service_unavailable", "Author search is unavailable") from exc
    inst = await institution_names([d["institution_id"] for d in docs if d.get("institution_id")])
    return [
        AuthorOption(
            author_id=d["_id"],
            name=d["name"],
            institution_name=inst.get(d.get("institution_id")),
            paper_count=d["n"],
        )
        for d in docs
    ]
