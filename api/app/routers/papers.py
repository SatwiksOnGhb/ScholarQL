"""Paper, citation and trend endpoints. Owned by Person A.

PLACEHOLDER: serves the fake catalog in app/fake_data.py, in the agreed shapes.
TODO(A): replace with queries on paper/author/venue/topic/authorship/citation
(citation_chain() for /citations, the topic-by-year materialized view for /trends).
"""

from collections import deque

from fastapi import APIRouter, Query

from app import fake_data as fake
from app.errors import ApiError
from app.models.common import NOT_FOUND
from app.models.papers import (
    CitationEdge,
    CitationGraph,
    CitationNode,
    Paper,
    PaperAuthor,
    TopicTrend,
    TrendsResponse,
    YearCount,
)

router = APIRouter(tags=["papers"])


def _get_fake_paper(paper_id: int) -> dict:
    paper = fake.PAPERS.get(paper_id)
    if paper is None:
        raise ApiError(404, "not_found", f"Paper {paper_id} not found")
    return paper


@router.get("/papers/{paper_id}", responses=NOT_FOUND)
async def get_paper(paper_id: int) -> Paper:
    p = _get_fake_paper(paper_id)
    authors = []
    for order, author_id in enumerate(p["author_ids"], start=1):
        a = fake.AUTHORS[author_id]
        authors.append(
            PaperAuthor(
                author_id=author_id,
                name=a["name"],
                author_order=order,
                institution=fake.INSTITUTIONS[a["institution_id"]],
            )
        )
    return Paper(
        paper_id=paper_id,
        title=p["title"],
        year=p["year"],
        venue=fake.VENUES[p["venue_id"]],
        authors=authors,
        topics=[fake.TOPICS[t] for t in p["topic_ids"]],
        citation_count=p["citation_count"],
        pagerank=round(p["citation_count"] / 1000, 4),
        abstract="Placeholder abstract. The real one comes from MongoDB paper_content.",
        tldr=p["tldr"],
    )


@router.get("/papers/{paper_id}/citations", responses=NOT_FOUND)
async def get_citations(paper_id: int, depth: int = Query(2, ge=1, le=3)) -> CitationGraph:
    _get_fake_paper(paper_id)
    # Breadth-first walk over citations in both directions (what it cites, what cites it)
    seen = {paper_id: 0}
    edges: set[tuple[int, int]] = set()
    queue = deque([paper_id])
    while queue:
        current = queue.popleft()
        if seen[current] == depth:
            continue
        for citing, cited in fake.CITATIONS:
            if current not in (citing, cited):
                continue
            edges.add((citing, cited))
            other = cited if citing == current else citing
            if other not in seen:
                seen[other] = seen[current] + 1
                queue.append(other)
    nodes = [
        CitationNode(
            paper_id=pid, title=fake.PAPERS[pid]["title"], year=fake.PAPERS[pid]["year"], depth=d
        )
        for pid, d in seen.items()
    ]
    return CitationGraph(
        root_id=paper_id,
        depth=depth,
        nodes=nodes,
        edges=[CitationEdge(citing_id=c, cited_id=d) for c, d in sorted(edges)],
    )


@router.get("/trends")
async def get_trends() -> TrendsResponse:
    years = range(2018, 2025)
    # Made-up yearly paper counts per topic
    fake_counts = {
        4001: [120, 180, 260, 340, 410, 520, 610],
        4002: [150, 170, 210, 250, 270, 300, 320],
        4003: [40, 60, 110, 190, 320, 480, 650],
        4004: [90, 110, 130, 140, 150, 160, 170],
    }
    topics = [
        TopicTrend(
            topic_id=topic_id,
            name=fake.TOPICS[topic_id]["name"],
            counts=[YearCount(year=y, count=c) for y, c in zip(years, counts, strict=True)],
            growth=round(counts[-1] / counts[0] - 1, 2),
        )
        for topic_id, counts in fake_counts.items()
    ]
    topics.sort(key=lambda t: t.growth, reverse=True)
    return TrendsResponse(from_year=years[0], to_year=years[-1], topics=topics)
