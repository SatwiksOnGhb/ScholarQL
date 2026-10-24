"""Reviewer finder with a conflict-of-interest check. Owned by Person C."""

from fastapi import APIRouter, Query, Request

from app.config import settings
from app.limits import limiter
from app.models.common import ErrorResponse
from app.models.reviewers import AuthorsResponse, ReviewerRequest, ReviewerResponse
from app.services.reviewers import find_reviewers, search_authors

router = APIRouter(prefix="/reviewers", tags=["reviewers"])

UNAVAILABLE = {503: {"model": ErrorResponse, "description": "MongoDB unavailable"}}


@router.post("", responses=UNAVAILABLE)
@limiter.limit(settings.rate_limit_heavy)  # embeds the abstract on every call
async def suggest_reviewers(request: Request, body: ReviewerRequest) -> ReviewerResponse:
    return await find_reviewers(body.abstract.strip(), body.author_ids, body.k)


@router.get("/authors", responses=UNAVAILABLE)
async def authors(
    q: str = Query(min_length=2, max_length=100, description="Part of an author's name"),
    limit: int = Query(10, ge=1, le=50),
) -> AuthorsResponse:
    """Author picker for the submitting-authors field."""
    return AuthorsResponse(authors=await search_authors(q.strip(), limit))
