"""Shapes for A's endpoints: /papers, /papers/{id}, /papers/{id}/citations, /trends.

IDs are OpenAlex short IDs as strings (papers "W…", authors "A…", venues "S…", institutions
"I…"), the text primary keys of A's PostgreSQL tables and the `_id`s in MongoDB. Topics are
arXiv categories ("cs.LG") or OpenAlex topic IDs ("T…").
"""

from pydantic import BaseModel, Field


class VenueRef(BaseModel):
    venue_id: str
    name: str
    type: str | None = Field(None, description="conference, journal, repository, …")


class InstitutionRef(BaseModel):
    institution_id: str
    name: str
    country: str | None = None


class PaperAuthor(BaseModel):
    author_id: str
    name: str
    author_order: int
    institution: InstitutionRef | None = Field(
        None, description="Affiliation on this paper's byline (author_affiliation)"
    )


class TopicRef(BaseModel):
    topic_id: str
    name: str


class Paper(BaseModel):
    paper_id: str
    title: str
    year: int | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    venue: VenueRef | None = None
    authors: list[PaperAuthor]
    topics: list[TopicRef]
    citation_count: int = Field(description="Citations from papers in the corpus")
    pagerank: float | None = Field(None, description="Influence score from compute_pagerank()")
    abstract: str | None = Field(None, description="From MongoDB paper_content")
    tldr: str | None = Field(None, description="From MongoDB paper_content")


class PaperListItem(BaseModel):
    paper_id: str
    title: str
    year: int | None = None
    venue_name: str | None = None
    authors: list[str] = Field(description="Author names in byline order")
    citation_count: int
    pagerank: float | None = None


class PaperList(BaseModel):
    items: list[PaperListItem]
    total: int
    limit: int
    offset: int


class CitationNode(BaseModel):
    paper_id: str
    title: str
    year: int | None = None
    depth: int = Field(description="Hops from the root paper (root = 0)")


class CitationEdge(BaseModel):
    citing_id: str
    cited_id: str


class CitationGraph(BaseModel):
    """Papers the root builds on and papers that build on it, up to `depth` hops."""

    root_id: str
    depth: int
    nodes: list[CitationNode]
    edges: list[CitationEdge]
    truncated: bool = Field(False, description="True if the node cap cut the walk short")


class YearCount(BaseModel):
    year: int
    count: int


class TopicTrend(BaseModel):
    topic_id: str
    name: str
    counts: list[YearCount]
    growth: float = Field(description="Relative change in papers per year over the window")


class TrendsResponse(BaseModel):
    from_year: int
    to_year: int
    topics: list[TopicTrend]
