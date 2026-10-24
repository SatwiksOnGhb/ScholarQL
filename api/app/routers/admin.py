"""Usage analytics. Owned by Person C."""

from fastapi import APIRouter, Query

from app.models.admin import AdminStats
from app.models.common import ErrorResponse
from app.services.analytics import get_stats

router = APIRouter(prefix="/admin", tags=["admin"])

UNAVAILABLE = {503: {"model": ErrorResponse, "description": "MongoDB unavailable"}}


@router.get("/stats", responses=UNAVAILABLE)
async def stats(
    weeks: int = Query(8, ge=1, le=52, description="Window: last N weeks"),
) -> AdminStats:
    """Accuracy by route and week, latency percentiles, top questions, failure reasons."""
    return await get_stats(weeks)
