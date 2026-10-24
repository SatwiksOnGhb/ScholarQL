"""Semantic search over papers. Owned by Person C.

PLACEHOLDER: ranks the fake catalog by keyword overlap.
Task 8 replaces this with vector_search() over MongoDB plus a PostgreSQL join for titles.
"""

from fastapi import APIRouter, Query

from app import fake_data as fake
from app.models.search import SearchHit, SearchResponse

router = APIRouter(tags=["search"])


@router.get("/search")
async def search(
    q: str = Query(min_length=1, max_length=500),
    k: int = Query(10, ge=1, le=50),
    year_from: int | None = Query(None, ge=1900, le=2100),
    venue_id: int | None = None,
) -> SearchResponse:
    words = set(q.lower().split())
    hits = []
    for p in fake.PAPERS.values():
        if year_from is not None and p["year"] < year_from:
            continue
        if venue_id is not None and p["venue_id"] != venue_id:
            continue
        text = f"{p['title']} {p['tldr']}".lower()
        overlap = sum(w in text for w in words)
        hits.append(
            SearchHit(
                paper_id=p["paper_id"],
                score=round(0.5 + 0.5 * overlap / len(words), 3),
                title=p["title"],
                year=p["year"],
                venue_id=p["venue_id"],
                venue_name=fake.VENUES[p["venue_id"]]["name"],
                tldr=p["tldr"],
            )
        )
    hits.sort(key=lambda h: h.score, reverse=True)
    return SearchResponse(query=q, results=hits[:k])
