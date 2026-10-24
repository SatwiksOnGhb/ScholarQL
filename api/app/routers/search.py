"""Semantic search over papers. Owned by Person C."""

from fastapi import APIRouter, Query

from app.models.common import ErrorResponse
from app.models.search import SearchResponse, VenueOption, VenuesResponse
from app.services.paper_lookup import top_venues
from app.services.vector_search import VectorFilters, search_papers

router = APIRouter(prefix="/search", tags=["search"])

UNAVAILABLE = {503: {"model": ErrorResponse, "description": "MongoDB unavailable"}}


@router.get("", responses=UNAVAILABLE)
async def search(
    q: str = Query(min_length=1, max_length=500, description="What the papers should be about"),
    k: int = Query(10, ge=1, le=50),
    year_from: int | None = Query(None, ge=1900, le=2100),
    venue_id: int | None = None,
) -> SearchResponse:
    filters: VectorFilters = {}
    if year_from is not None:
        filters["year_from"] = year_from
    if venue_id is not None:
        filters["venue_id"] = venue_id
    return SearchResponse(query=q, results=await search_papers(q.strip(), k, filters))


@router.get("/venues")
async def venues(limit: int = Query(50, ge=1, le=200)) -> VenuesResponse:
    """Venues with the most papers, for the search page's venue filter."""
    return VenuesResponse(
        venues=[
            VenueOption(venue_id=v.venue_id, name=v.name, paper_count=v.paper_count)
            for v in await top_venues(limit)
        ]
    )
