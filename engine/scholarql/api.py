"""Same-origin FastAPI service and compiled React application."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StringConstraints
from pymongo.errors import PyMongoError

from .config import DATA, ROOT
from .db import DB_ERRORS, read_pilot
from .engine import RANK_NAMES, SearchEngine
from .providers import Strategy


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = SearchEngine.from_environment()
    app.state.engine = engine
    try:
        yield
    finally:
        engine.documents.close()


app = FastAPI(title="ScholarQL", version="1.0.0", lifespan=lifespan)


class SearchRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=900)]
    route: Literal["auto", "sql", "semantic", "hybrid"] = "auto"
    generator: Literal["local", "gemini", "groq"] = "local"
    strategy: Strategy = "few_shot_correction"
    k: int = Field(default=8, ge=1, le=20)


@app.exception_handler(DB_ERRORS[0])
@app.exception_handler(DB_ERRORS[1])
def database_error(_request: Request, _error: Exception):
    return JSONResponse(
        status_code=503,
        content={"detail": "The relational database is unavailable or the query timed out."},
    )


def get_engine(request):
    return request.app.state.engine


@lru_cache(maxsize=1)
def pilot_metadata():
    return read_pilot()["metadata"]


@app.get("/api/status")
def status(request: Request):
    engine = get_engine(request)
    db = engine.db
    stats = db.run("""
SELECT (SELECT count(*) FROM paper), (SELECT count(*) FROM author),
       (SELECT count(*) FROM citation), (SELECT count(*) FROM venue),
       (SELECT min(publication_year) FROM paper), (SELECT max(publication_year) FROM paper)
""").rows[0]
    totals = dict(zip(("papers", "authors", "citations", "venues", "year_from", "year_to"), stats))
    label = os.getenv("SCHOLARQL_CORPUS_LABEL") if db.postgres else pilot_metadata()["label"]
    return {
        "relational": db.engine,
        "documents": engine.documents.name,
        "retriever": RANK_NAMES[engine.retrieval],
        "corpus": label or "Configured corpus",
        "totals": totals,
        "scope": pilot_metadata()["scope"] if label == pilot_metadata()["label"] else "",
        "providers": {name: provider.model for name, provider in engine.providers.items()},
    }


@app.post("/api/query")
def query(body: SearchRequest, request: Request):
    return get_engine(request).search(
        body.question, body.route, body.generator, body.strategy, body.k
    )


@app.get("/api/papers")
def papers(
    request: Request,
    q: str = Query(default="", max_length=150),
    year: int | None = Query(default=None, ge=1800, le=2100),
    topic: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=18, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
):
    db = get_engine(request).db
    terms, values = [], []
    if q.strip():
        terms.append("(strpos(lower(p.title), lower(?)) > 0 OR p.arxiv_id = ?)")
        values.extend([q.strip(), q.strip()])
    if year is not None:
        terms.append("p.publication_year = ?")
        values.append(year)
    if topic:
        terms.append(
            "EXISTS (SELECT 1 FROM paper_topic pt WHERE pt.paper_id = p.paper_id AND pt.topic_id = ?)"
        )
        values.append(topic)
    where = "WHERE " + " AND ".join(terms) if terms else ""
    total = db.run(f"SELECT count(*) FROM paper p {where}", tuple(values)).rows[0][0]
    rows = db.run(
        f"""
SELECT p.paper_id, p.title, p.publication_year, p.doi, p.arxiv_id, p.cited_by_count, v.name AS venue
FROM paper p LEFT JOIN venue v USING (venue_id) {where}
ORDER BY p.publication_year DESC NULLS LAST, p.cited_by_count DESC, p.paper_id
LIMIT ? OFFSET ?
""",
        (*values, limit, offset),
        cap=limit,
    ).records()
    return {"items": rows, "total": total, "offset": offset, "limit": limit}


@app.get("/api/papers/{paper_id}")
def paper(paper_id: str, request: Request):
    engine = get_engine(request)
    db = engine.db
    rows = db.run(
        """
SELECT p.paper_id, p.title, p.publication_year, p.publication_date, p.arxiv_id, p.doi,
       p.cited_by_count, p.pagerank_score, v.name AS venue
FROM paper p LEFT JOIN venue v USING (venue_id) WHERE p.paper_id = ?
""",
        (paper_id,),
    ).records()
    if not rows:
        raise HTTPException(404, "Paper unavailable in this corpus.")
    people = db.run(
        """
SELECT a.author_id, a.name FROM author a JOIN authorship au USING (author_id)
WHERE au.paper_id = ? ORDER BY au.author_order
""",
        (paper_id,),
        cap=2000,
    ).records()
    topics = db.run(
        """
SELECT t.name FROM paper_topic pt JOIN topic t USING (topic_id)
WHERE pt.paper_id = ? ORDER BY pt.is_primary DESC, t.name
""",
        (paper_id,),
    ).records()
    try:
        document = engine.documents.get(paper_id)
        content_status = "available" if document else "missing"
    except PyMongoError:
        document, content_status = {}, "unavailable"
    return {
        **rows[0],
        "authors": people,
        "topics": [t["name"] for t in topics],
        "abstract": document.get("abstract"),
        "tldr": document.get("tldr"),
        "sources": document.get("sources", {}),
        "content_status": content_status,
    }


@app.get("/api/citations/{paper_id}")
def citations(
    paper_id: str,
    request: Request,
    depth: int = Query(default=2, ge=1, le=5),
    direction: Literal["outgoing", "incoming"] = "outgoing",
):
    db = get_engine(request).db
    root = db.run("SELECT paper_id, title FROM paper WHERE paper_id = ?", (paper_id,)).records()
    if not root:
        raise HTTPException(404, "Paper unavailable in this corpus.")
    first, second = (
        ("citing_id", "cited_id") if direction == "outgoing" else ("cited_id", "citing_id")
    )
    rows = db.run(
        f"""
WITH RECURSIVE frontier(paper_id, distance) AS (
  SELECT paper_id, 0 FROM paper WHERE paper_id = ?
  UNION
  SELECT c.{second}, f.distance + 1
  FROM frontier f JOIN citation c ON c.{first} = f.paper_id
  WHERE f.distance < ?
), layers AS (
  SELECT paper_id, min(distance) AS level FROM frontier GROUP BY paper_id
)
SELECT e.citing_id, e.cited_id, a.title AS from_title, b.title AS to_title, f.level AS from_level, t.level AS to_level
FROM layers f JOIN citation e ON e.{first} = f.paper_id JOIN layers t ON t.paper_id = e.{second}
JOIN paper a ON a.paper_id = e.{first} JOIN paper b ON b.paper_id = e.{second}
WHERE t.level = f.level + 1
ORDER BY t.level, e.{first}, e.{second} LIMIT 121
""",
        (paper_id, depth),
        cap=120,
    )
    return {
        "root": root[0],
        "depth": depth,
        "direction": direction,
        "edges": rows.records(),
        "truncated": rows.truncated,
    }


@app.get("/api/trends")
def trends(request: Request, topic: str | None = Query(default=None, max_length=100)):
    db = get_engine(request).db
    topics = db.run("SELECT topic_id, name FROM topic ORDER BY name LIMIT 250", cap=250).records()
    if topic is not None:
        result = db.run(
            "SELECT topic_name, publication_year, paper_count FROM topic_year_trends WHERE topic_id = ? ORDER BY publication_year",
            (topic,),
        )
    else:
        result = db.run("""
SELECT 'All papers' AS topic_name, publication_year, count(*) AS paper_count FROM paper
WHERE publication_year IS NOT NULL GROUP BY publication_year ORDER BY publication_year
""")
    return {"items": result.records(), "topics": topics}


@app.get("/api/history")
def history(request: Request):
    try:
        return {"items": get_engine(request).documents.get_logs()}
    except PyMongoError:
        raise HTTPException(503, "Query history is unavailable.")


RESULTS = ROOT / "results"
FILES = {
    "evaluation": "evaluation.json",
    "sql": "sql_cases.csv",
    "retrieval": "retrieval_cases.csv",
    "indexes": "index_summary.csv",
    "plans": "index_plans.json",
    "timings": "index_timings.csv",
    "benchmark": "sql_benchmark.jsonl",
    "qrels": "retrieval_qrels.jsonl",
}
DIST = ROOT / "web" / "dist"


@app.get("/api/artifacts/{name}")
def artifact(name: str):
    basename = FILES.get(name)
    directory = DATA if name in {"benchmark", "qrels"} else RESULTS
    if not basename or not (directory / basename).is_file():
        raise HTTPException(404, "This study artifact is unavailable.")
    return FileResponse(directory / basename, filename=basename)


if (DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="frontend")


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    if path.startswith(("api/", "assets/")):
        raise HTTPException(404, "Resource unavailable.")
    if path == "mark.svg" and (DIST / path).exists():
        return FileResponse(DIST / path)
    index = DIST / "index.html"
    if not index.is_file():
        return JSONResponse(
            status_code=503, content={"detail": "Build the frontend with npm run build in web/."}
        )
    return FileResponse(index)
