"""Shapes for the reviewer finder (POST /reviewers) and its author picker."""

from typing import Literal

from pydantic import BaseModel, Field


class ReviewerRequest(BaseModel):
    abstract: str = Field(min_length=20, max_length=5000)
    author_ids: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Submitting authors; they, their co-authors and same-institution "
        "authors are excluded",
    )
    k: int = Field(10, ge=1, le=50)


class MatchingPaper(BaseModel):
    paper_id: str
    title: str
    year: int | None = None
    score: float


class Reviewer(BaseModel):
    author_id: str
    name: str
    institution_id: str | None = None
    institution_name: str | None = None
    score: float = Field(description="Similarity of the author's profile to the abstract (0..1)")
    paper_count: int
    matching_papers: list[MatchingPaper] = Field(
        description="The author's papers closest to the abstract: why they were suggested"
    )


class ExcludedAuthor(BaseModel):
    author_id: str
    name: str | None = None
    reason: Literal["submitting_author", "coauthor"]


class ExcludedInstitution(BaseModel):
    institution_id: str
    name: str | None = None


class ReviewerResponse(BaseModel):
    reviewers: list[Reviewer]
    excluded_authors: list[ExcludedAuthor] = Field(
        description="Dropped by the conflict-of-interest check"
    )
    excluded_institutions: list[ExcludedInstitution] = Field(
        description="Institutions of the submitting authors; nobody from them is suggested"
    )


class AuthorOption(BaseModel):
    author_id: str
    name: str
    institution_name: str | None = None
    paper_count: int


class AuthorsResponse(BaseModel):
    authors: list[AuthorOption]
