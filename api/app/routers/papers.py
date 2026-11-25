"""Paper, citation and trend endpoints (Person A's relational core).

SQL adapted from A's API (scholarql.zip) to the shared response shapes in app/models/papers.py.
It reads A's tables (paper, venue, author, authorship, author_affiliation, institution, topic,
paper_topic, citation) and the topic_year_trends materialized view. Abstracts and TLDRs come
from MongoDB paper_content.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
from fastapi import APIRouter, Query
from psycopg.rows import dict_row
from pymongo.errors import PyMongoError

from app.db import mongo, postgres
from app.errors import ApiError
from app.models.common import NOT_FOUND, ErrorResponse
from app.models.papers import (
    CitationEdge,
    CitationGraph,
    CitationNode,
    InstitutionRef,
    Paper,
    PaperAuthor,
    PaperList,
    PaperListItem,
    TopicRef,
    TopicTrend,
    TrendsResponse,
    VenueRef,
    YearCount,
)
from app.services.paper_lookup import NOT_READY

log = logging.getLogger(__name__)
router = APIRouter(tags=["papers"])

UNAVAILABLE = {503: {"model": ErrorResponse, "description": "PostgreSQL unavailable"}}
MAX_GRAPH_NODES = 300


@asynccontextmanager
async def _conn() -> AsyncIterator[psycopg.AsyncConnection]:
    try:
        async with postgres.get_pool().connection(timeout=3) as conn:
            conn.row_factory = dict_row
            yield conn
    except NOT_READY as exc:
        log.warning("PostgreSQL not ready: %s", exc)
        raise ApiError(503, "service_unavailable", "The paper database is unavailable") from exc


@router.get("/papers", responses=UNAVAILABLE)
async def list_papers(
    q: str | None = Query(None, max_length=200, description="Words in the title"),
    year_from: int | None = Query(None, ge=1800, le=2100),
    year_to: int | None = Query(None, ge=1800, le=2100),
    venue_id: str | None = Query(None, max_length=64),
    sort: str = Query("citations", pattern="^(citations|pagerank|year)$"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100_000),
) -> PaperList:
    """Browse papers with simple filters, most cited first by default."""
    if year_from and year_to and year_from > year_to:
        raise ApiError(422, "validation_error", "year_from must be <= year_to")
    clauses, params = [], []
    if q:
        clauses.append("p.title ILIKE %s")
        params.append(f"%{q.strip()}%")
    if year_from is not None:
        clauses.append("p.publication_year >= %s")
        params.append(year_from)
    if year_to is not None:
        clauses.append("p.publication_year <= %s")
        params.append(year_to)
    if venue_id:
        clauses.append("p.venue_id = %s")
        params.append(venue_id)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    order = {
        "citations": "p.cited_by_count DESC, p.pagerank_score DESC",
        "pagerank": "p.pagerank_score DESC, p.cited_by_count DESC",
        "year": "p.publication_year DESC NULLS LAST, p.cited_by_count DESC",
    }[sort]
    sql = f"""
        SELECT p.paper_id, p.title, p.publication_year, v.name AS venue_name,
               p.cited_by_count, p.pagerank_score, count(*) OVER () AS total,
               coalesce((SELECT array_agg(a.name ORDER BY au.author_order)
                         FROM authorship au JOIN author a USING (author_id)
                         WHERE au.paper_id = p.paper_id), '{{}}') AS authors
        FROM paper p LEFT JOIN venue v USING (venue_id)
        {where}
        ORDER BY {order}, p.paper_id
        LIMIT %s OFFSET %s"""
    async with _conn() as conn:
        rows = await (await conn.execute(sql, [*params, limit, offset])).fetchall()
    return PaperList(
        items=[
            PaperListItem(
                paper_id=r["paper_id"],
                title=r["title"],
                year=r["publication_year"],
                venue_name=r["venue_name"],
                authors=list(r["authors"]),
                citation_count=r["cited_by_count"],
                pagerank=r["pagerank_score"],
            )
            for r in rows
        ],
        total=rows[0]["total"] if rows else 0,
        limit=limit,
        offset=offset,
    )


@router.get("/papers/{paper_id}", responses={**NOT_FOUND, **UNAVAILABLE})
async def get_paper(paper_id: str) -> Paper:
    async with _conn() as conn:
        p = await (
            await conn.execute(
                """SELECT p.paper_id, p.title, p.publication_year, p.doi, p.arxiv_id,
                          p.cited_by_count, p.pagerank_score,
                          v.venue_id, v.name AS venue_name, v.venue_type
                   FROM paper p LEFT JOIN venue v USING (venue_id)
                   WHERE p.paper_id = %s""",
                (paper_id,),
            )
        ).fetchone()
        if p is None:
            raise ApiError(404, "not_found", f"Paper {paper_id} not found")
        authors = await (
            await conn.execute(
                """SELECT au.author_id, a.name, au.author_order,
                          aff.institution_id, i.name AS institution_name, i.country_code
                   FROM authorship au
                   JOIN author a USING (author_id)
                   LEFT JOIN LATERAL (
                       SELECT institution_id FROM author_affiliation af
                       WHERE af.paper_id = au.paper_id AND af.author_id = au.author_id
                       ORDER BY institution_id LIMIT 1
                   ) aff ON true
                   LEFT JOIN institution i ON i.institution_id = aff.institution_id
                   WHERE au.paper_id = %s
                   ORDER BY au.author_order""",
                (paper_id,),
            )
        ).fetchall()
        topics = await (
            await conn.execute(
                """SELECT t.topic_id, t.name FROM paper_topic pt JOIN topic t USING (topic_id)
                   WHERE pt.paper_id = %s
                   ORDER BY pt.is_primary DESC, pt.relevance DESC NULLS LAST, t.name""",
                (paper_id,),
            )
        ).fetchall()

    content: dict = {}
    try:
        content = (
            await mongo.get_db().paper_content.find_one(
                {"_id": paper_id}, {"abstract": 1, "tldr": 1}
            )
            or {}
        )
    except PyMongoError as exc:  # the page still works without the abstract
        log.warning("paper_content unavailable: %s", exc)

    return Paper(
        paper_id=p["paper_id"],
        title=p["title"],
        year=p["publication_year"],
        doi=p["doi"],
        arxiv_id=p["arxiv_id"],
        venue=VenueRef(venue_id=p["venue_id"], name=p["venue_name"], type=p["venue_type"])
        if p["venue_id"]
        else None,
        authors=[
            PaperAuthor(
                author_id=a["author_id"],
                name=a["name"],
                author_order=a["author_order"],
                institution=InstitutionRef(
                    institution_id=a["institution_id"],
                    name=a["institution_name"],
                    country=a["country_code"],
                )
                if a["institution_id"]
                else None,
            )
            for a in authors
        ],
        topics=[TopicRef(topic_id=t["topic_id"], name=t["name"]) for t in topics],
        citation_count=p["cited_by_count"],
        pagerank=p["pagerank_score"],
        abstract=content.get("abstract"),
        tldr=content.get("tldr"),
    )


@router.get("/papers/{paper_id}/citations", responses={**NOT_FOUND, **UNAVAILABLE})
async def get_citations(paper_id: str, depth: int = Query(2, ge=1, le=3)) -> CitationGraph:
    """Breadth-first walk over the citation table in both directions (what the paper cites
    and what cites it), one indexed query per hop, capped at MAX_GRAPH_NODES papers."""
    async with _conn() as conn:
        root = await (
            await conn.execute("SELECT 1 FROM paper WHERE paper_id = %s", (paper_id,))
        ).fetchone()
        if root is None:
            raise ApiError(404, "not_found", f"Paper {paper_id} not found")

        seen = {paper_id: 0}
        edges: set[tuple[str, str]] = set()
        frontier = [paper_id]
        truncated = False
        for level in range(1, depth + 1):
            if not frontier:
                break
            rows = await (
                await conn.execute(
                    """SELECT citing_id, cited_id FROM citation
                       WHERE citing_id = ANY(%s) OR cited_id = ANY(%s)""",
                    (frontier, frontier),
                )
            ).fetchall()
            next_frontier = []
            for r in rows:
                for other in (r["citing_id"], r["cited_id"]):
                    if other in seen:
                        continue
                    if len(seen) >= MAX_GRAPH_NODES:
                        truncated = True
                        continue
                    seen[other] = level
                    next_frontier.append(other)
                if r["citing_id"] in seen and r["cited_id"] in seen:
                    edges.add((r["citing_id"], r["cited_id"]))
            frontier = next_frontier

        papers = await (
            await conn.execute(
                "SELECT paper_id, title, publication_year FROM paper WHERE paper_id = ANY(%s)",
                (list(seen),),
            )
        ).fetchall()
    info = {r["paper_id"]: r for r in papers}
    nodes = sorted(
        (
            CitationNode(
                paper_id=pid,
                title=info[pid]["title"],
                year=info[pid]["publication_year"],
                depth=d,
            )
            for pid, d in seen.items()
            if pid in info
        ),
        key=lambda n: (n.depth, n.paper_id),
    )
    return CitationGraph(
        root_id=paper_id,
        depth=depth,
        nodes=nodes,
        edges=[CitationEdge(citing_id=c, cited_id=d) for c, d in sorted(edges)],
        truncated=truncated,
    )


def growth(counts: list[int]) -> float:
    """Relative change from the first to the last year of the window (0 if it started at 0)."""
    first, last = counts[0], counts[-1]
    if first == 0:
        return float(last)
    return round(last / first - 1, 2)


@router.get("/trends", responses=UNAVAILABLE)
async def get_trends(
    year_from: int = Query(2018, ge=1800, le=2100),
    year_to: int = Query(2024, ge=1800, le=2100),
    limit: int = Query(8, ge=1, le=40, description="Topics with the most papers in the window"),
) -> TrendsResponse:
    """Papers per topic per year, from A's topic_year_trends materialized view."""
    if year_from > year_to:
        raise ApiError(422, "validation_error", "year_from must be <= year_to")
    async with _conn() as conn:
        rows = await (
            await conn.execute(
                """WITH top AS (
                       SELECT topic_id FROM topic_year_trends
                       WHERE publication_year BETWEEN %(lo)s AND %(hi)s
                       GROUP BY topic_id
                       ORDER BY sum(paper_count) DESC, topic_id
                       LIMIT %(limit)s
                   )
                   SELECT t.topic_id, t.topic_name, t.publication_year, t.paper_count
                   FROM topic_year_trends t JOIN top USING (topic_id)
                   WHERE t.publication_year BETWEEN %(lo)s AND %(hi)s""",
                {"lo": year_from, "hi": year_to, "limit": limit},
            )
        ).fetchall()

    years = list(range(year_from, year_to + 1))
    by_topic: dict[str, dict] = {}
    for r in rows:
        entry = by_topic.setdefault(r["topic_id"], {"name": r["topic_name"], "counts": {}})
        entry["counts"][r["publication_year"]] = r["paper_count"]
    topics = []
    for topic_id, entry in by_topic.items():
        counts = [entry["counts"].get(y, 0) for y in years]
        topics.append(
            TopicTrend(
                topic_id=topic_id,
                name=entry["name"],
                counts=[YearCount(year=y, count=c) for y, c in zip(years, counts, strict=True)],
                growth=growth(counts),
            )
        )
    topics.sort(key=lambda t: sum(c.count for c in t.counts), reverse=True)
    return TrendsResponse(from_year=year_from, to_year=year_to, topics=topics)
