"""Shapes for A's endpoints: /papers/{id}, /papers/{id}/citations, /trends.

IDs are OpenAlex numbers (W2741809807 -> 2741809807), the same keys as in PostgreSQL and MongoDB.
"""

from pydantic import BaseModel, Field


class VenueRef(BaseModel):
    venue_id: int
    name: str
    type: str | None = Field(None, description="conference or journal")


class InstitutionRef(BaseModel):
    institution_id: int
    name: str
    country: str | None = None


class PaperAuthor(BaseModel):
    author_id: int
    name: str
    author_order: int
    institution: InstitutionRef | None = None


class TopicRef(BaseModel):
    topic_id: int
    name: str


class Paper(BaseModel):
    paper_id: int
    title: str
    year: int
    doi: str | None = None
    arxiv_id: str | None = None
    venue: VenueRef | None = None
    authors: list[PaperAuthor]
    topics: list[TopicRef]
    citation_count: int
    pagerank: float | None = Field(None, description="Influence score from compute_pagerank()")
    abstract: str | None = Field(None, description="From MongoDB paper_content")
    tldr: str | None = Field(None, description="From MongoDB paper_content")


class CitationNode(BaseModel):
    paper_id: int
    title: str
    year: int
    depth: int = Field(description="Hops from the root paper (root = 0)")


class CitationEdge(BaseModel):
    citing_id: int
    cited_id: int


class CitationGraph(BaseModel):
    """Papers the root builds on and papers that build on it, up to `depth` hops."""

    root_id: int
    depth: int
    nodes: list[CitationNode]
    edges: list[CitationEdge]


class YearCount(BaseModel):
    year: int
    count: int


class TopicTrend(BaseModel):
    topic_id: int
    name: str
    counts: list[YearCount]
    growth: float = Field(description="Relative change in papers per year over the window")


class TrendsResponse(BaseModel):
    from_year: int
    to_year: int
    topics: list[TopicTrend]
