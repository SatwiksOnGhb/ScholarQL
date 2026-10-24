"""Shapes for GET /search (semantic search over MongoDB, joined with PostgreSQL)."""

from pydantic import BaseModel, Field


class SearchHit(BaseModel):
    paper_id: int
    score: float = Field(description="Vector search score (cosine-based, 0..1), higher is closer")
    title: str
    year: int | None = None
    venue_id: int | None = None
    venue_name: str | None = None
    tldr: str | None = None
    abstract: str | None = Field(None, description="Start of the abstract (about 400 chars)")


class SearchResponse(BaseModel):
    query: str
    results: list[SearchHit]


class VenueOption(BaseModel):
    venue_id: int
    name: str
    paper_count: int


class VenuesResponse(BaseModel):
    venues: list[VenueOption]
