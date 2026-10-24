"""Shapes for GET /search (semantic search over MongoDB, joined with PostgreSQL)."""

from pydantic import BaseModel, Field


class SearchHit(BaseModel):
    paper_id: int
    score: float = Field(description="Cosine similarity, higher is closer")
    title: str
    year: int | None = None
    venue_id: int | None = None
    venue_name: str | None = None
    tldr: str | None = None


class SearchResponse(BaseModel):
    query: str
    results: list[SearchHit]
