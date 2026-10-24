"""Shapes for POST /reviewers (reviewer finder with a conflict-of-interest check)."""

from pydantic import BaseModel, Field


class ReviewerRequest(BaseModel):
    abstract: str = Field(min_length=20, max_length=5000)
    author_ids: list[int] = Field(
        default_factory=list,
        description="Submitting authors; they, their co-authors and same-institution "
        "authors are excluded",
    )
    k: int = Field(10, ge=1, le=50)


class MatchingPaper(BaseModel):
    paper_id: int
    title: str
    score: float


class Reviewer(BaseModel):
    author_id: int
    name: str
    institution_id: int | None = None
    institution_name: str | None = None
    score: float = Field(description="Similarity of the author's profile to the abstract")
    matching_papers: list[MatchingPaper] = Field(description="Why this reviewer was suggested")


class ReviewerResponse(BaseModel):
    reviewers: list[Reviewer]
    excluded_author_ids: list[int] = Field(description="Dropped by the conflict-of-interest check")
