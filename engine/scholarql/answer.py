"""Contract 3: `answer(question) -> dict` with the fields of the API's `Answer` model.

A thin layer over B's SearchEngine (engine.py) for the shared FastAPI app:

- PostgreSQL: B's read-only `Database` with A's `scholarql_reader` role.
- Documents: C's MongoDB `paper_content` (abstracts and bge-small vectors) instead of B's own
  `paper_documents` collection, so the semantic and hybrid routes rank with the same
  embeddings as /search and the reviewer finder.
- Logging: off here. The API's log_query() writes every question to `query_logs` in the
  validated shape (B's own log records don't match it).

The engine is synchronous (psycopg/pymongo, CPU ranking); the API calls answer() in a
worker thread.
"""

from __future__ import annotations

import os
import re
import threading
from collections.abc import Callable, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import numpy as np
from bson.binary import Binary
from pymongo import MongoClient

from .db import Database
from .documents import DocumentStore
from .engine import FILTER_CAP, SearchEngine
from .intents import (
    compile_question,
    extract_filters,
    route_question,
    unresolved_constraints,
    unsupported_filter_logic,
)
from .retrieval import TextIndex
from .safety import QueryError

Embedder = Callable[[str], Sequence[float]]

VECTOR_INDEX = "paper_embedding"  # mongo/vector-indexes.json
EXACT_LIMIT = 5_000  # up to this many filtered candidates, rank all of them exactly
TOP_K = 10


class EngineError(Exception):
    """The engine could not answer; the message is safe to show to the user."""


class UnsupportedQuestion(EngineError):
    """Outside what the engine can parse or rank (B's "unsupported" status)."""


class QueryFailed(EngineError):
    """The SQL was rejected or the database failed (B's "error" status)."""


class DocumentsUnavailable(EngineError):
    """MongoDB couldn't be reached for a semantic or hybrid question."""


MONGO_DOWN = "The document database is unavailable"  # B's diagnostic for PyMongoError


class ContentStore(DocumentStore):
    """B's DocumentStore interface over C's MongoDB paper_content + titles from PostgreSQL."""

    def __init__(self, mongo_uri: str, db_name: str, database: Database):
        self.name = "MongoDB"
        self.atlas_index = ""  # dense ranking is done by ScholarEngine._rank below
        self.client = MongoClient(mongo_uri, serverSelectionTimeoutMS=2500, socketTimeoutMS=8000)
        self.mongo = self.client[db_name]
        self.database = database
        self.local_path = None
        self.local = {}
        self.logging = False

    def _with_titles(self, docs: list[dict]) -> list[dict]:
        ids = [d["_id"] for d in docs]
        rows = self.database.run(
            "SELECT paper_id, title, publication_year FROM paper WHERE paper_id = ANY(?)",
            (ids,),
            cap=len(ids) or 1,
        ).rows
        meta = {pid: (title, year) for pid, title, year in rows}
        return [
            {
                "paper_id": d["_id"],
                "title": meta.get(d["_id"], (None, None))[0] or d["_id"],
                "abstract": d.get("abstract") or "",
                "publication_year": meta.get(d["_id"], (None, d.get("year")))[1],
            }
            for d in docs
        ]

    def all(self) -> list[dict]:
        docs = list(self.mongo.paper_content.find({}, {"abstract": 1, "year": 1}).limit(100_001))
        if len(docs) > 100_000:
            raise ValueError("Too many documents for the in-memory fallback index.")
        return self._with_titles(docs)

    def get(self, paper_id: str) -> dict:
        doc = self.mongo.paper_content.find_one({"_id": paper_id}, {"abstract": 1, "year": 1})
        return self._with_titles([doc])[0] if doc else {}

    def save_log(self, event: dict) -> bool:
        return False


class ScholarEngine(SearchEngine):
    """B's engine with the document ranking step swapped for C's MongoDB vectors."""

    def __init__(self, database: Database, documents: ContentStore, embed: Embedder):
        super().__init__(database, documents, "tfidf")
        self.embed = embed

    def _rank(self, output, filters, k):
        # Same guards as B's SearchEngine._rank
        if unresolved_constraints(filters.concept) or unsupported_filter_logic(output["question"]):
            output.update(
                status="unsupported",
                diagnostic='Use an explicit filter such as "since 2021", '
                'tagged "cs.LG", or at "arXiv" together with a research concept.',
            )
            return
        concept = (filters.concept or "").strip(" ,&")
        if not concept:
            output.update(
                status="unsupported", diagnostic="Add a research concept to rank the papers."
            )
            return
        output.update(sql=filters.sql, filters=list(filters.labels), concept=concept)

        eligible: set[str] | None = None
        if filters.conditions:
            rows = self.db.run(filters.sql, cap=FILTER_CAP)
            if rows.truncated:
                raise QueryError("More than 100,000 candidate papers. Add a year or topic filter.")
            eligible = {row[0] for row in rows.rows}
            output["candidates"] = len(eligible)

        ranking = self._dense(concept, eligible, k)
        if ranking is None:  # no vectors in MongoDB yet: B's TF-IDF over the abstracts
            index = TextIndex(self.documents.all())
            ranking = [
                (r["paper_id"], r["score"])
                for r in index.rank(concept, eligible=eligible, k=k, mode="tfidf")
            ]
            output["retriever"] = "TF-IDF cosine (no embeddings in MongoDB yet)"
        else:
            output["retriever"] = "bge-small cosine over MongoDB paper_content"

        ids = [pid for pid, _ in ranking]
        docs = {d["paper_id"]: d for d in self.documents._with_titles(self._content(ids))}
        output["papers"] = [
            {**docs[pid], "score": round(s, 4)} for pid, s in ranking if pid in docs
        ]
        output["status"] = "answered" if output["papers"] else "no_results"

    def _content(self, ids: list[str]) -> list[dict]:
        found = {
            d["_id"]: d
            for d in self.documents.mongo.paper_content.find(
                {"_id": {"$in": ids}}, {"abstract": 1, "year": 1}
            )
        }
        return [found[i] for i in ids if i in found]

    def _dense(self, concept: str, eligible: set[str] | None, k: int):
        """[(paper_id, score)] best first, score on Atlas's 0..1 scale; None without vectors."""
        coll = self.documents.mongo.paper_content
        if coll.find_one({"embedding": {"$exists": True}}, {"_id": 1}) is None:
            return None
        query = np.asarray(self.embed(concept), dtype=np.float32)

        if eligible is not None and len(eligible) <= EXACT_LIMIT:
            # Exact cosine over every allowed paper (vectors are unit length)
            ids, vectors = [], []
            for d in coll.find(
                {"_id": {"$in": list(eligible)}, "embedding": {"$exists": True}},
                {"embedding": 1},
            ):
                ids.append(d["_id"])
                emb = d["embedding"]  # packed float32 vector on Atlas, a list locally
                vectors.append(emb.as_vector().data if isinstance(emb, Binary) else emb)
            if not ids:
                return []
            scores = (np.asarray(vectors, dtype=np.float32) @ query + 1) / 2
            order = np.argsort(-scores)[:k]
            return [(ids[i], float(scores[i])) for i in order]

        # Approximate search with Atlas Vector Search; over-fetch when post-filtering
        limit = k if eligible is None else min(max(k * 50, 500), 2_000)
        pipeline = [
            {
                "$vectorSearch": {
                    "index": VECTOR_INDEX,
                    "path": "embedding",
                    "queryVector": query.tolist(),
                    "numCandidates": min(max(limit * 10, 100), 10_000),
                    "limit": limit,
                }
            },
            {"$project": {"score": {"$meta": "vectorSearchScore"}}},
        ]
        hits = [(d["_id"], float(d["score"])) for d in coll.aggregate(pipeline, maxTimeMS=8000)]
        if eligible is not None:
            hits = [h for h in hits if h[0] in eligible]
        return hits[:k]


_engine: ScholarEngine | None = None
_lock = threading.Lock()


def configure(*, database_url: str, mongodb_uri: str, mongodb_db: str, embed: Embedder) -> None:
    """Called once by the API at startup. Nothing connects until the first question."""
    global _engine
    with _lock:
        database = Database(database_url)
        _engine = ScholarEngine(database, ContentStore(mongodb_uri, mongodb_db, database), embed)


def close() -> None:
    global _engine
    with _lock:
        if _engine is not None:
            _engine.documents.close()
            _engine = None


LLM_ORDER = ("groq", "gemini")  # Groq (GPT-OSS-120B) is the benchmarked model

# Words that ask for an exact, structured answer (counts, rankings, lookups, citations...)
EXACT_WORDS = re.compile(
    r"\b(?:how many|number of|count|average|avg|mean|median|total|top|most|least|highest|"
    r"lowest|rank(?:ed|ing)?|which|who|when|list|show|arxiv|doi|cites?|cited|citations?|"
    r"authors?|venues?|institutions?|universit(?:y|ies)|per year|by year|h-index|pagerank)\b",
    re.I,
)


def _llms(engine: ScholarEngine) -> list[str]:
    return [g for g in LLM_ORDER if g in engine.providers]


def _generator(engine: ScholarEngine, question: str = "") -> str:
    """SCHOLARQL_GENERATOR = auto (default) | local | gemini | groq.

    auto = B's rule-based compiler when it recognises the question, otherwise an LLM (Groq,
    else Gemini). On the 100-question benchmark the compiler is exact on wording it knows
    (80/80) but can't parse paraphrases (0/20), while GPT-OSS-120B got 83-84/100 overall;
    compiler first, LLM as fallback scores 97-98/100 and keeps known questions fast.
    """
    choice = os.getenv("SCHOLARQL_GENERATOR", "auto").lower()
    if choice != "auto":
        return choice
    if question and compile_question(question):
        return "local"
    return next(iter(_llms(engine)), "local")


def _is_topic(question: str) -> bool:
    """A bare topic such as "diffusion models image generation": no structural request,
    so rank papers by meaning instead of asking an LLM for SQL."""
    if compile_question(question) or EXACT_WORDS.search(question):
        return False
    filters = extract_filters(question)
    return route_question(question, filters, None) == "sql" and len(question.split()) <= 12


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    return value


def _explanation(out: dict) -> str:
    if out["route"] == "sql":
        how = (
            "B's rule-based SQL compiler"
            if out["generator"] == "local"
            else f"{out['generator'].title()} ({out.get('model', 'LLM')}), {out['strategy']}"
        )
        checked = ", validated and planner-checked" if out.get("planner_checked") else ""
        rows = len(out["rows"])
        more = "+ (truncated)" if out.get("truncated") else ""
        return f"SQL generated by {how}{checked}; {rows}{more} rows."
    text = f'Papers ranked by meaning for "{out.get("concept", "")}" ({out.get("retriever")})'
    if out["route"] == "hybrid" and out.get("filters"):
        text += f", among {out.get('candidates', 0)} papers matching: " + "; ".join(out["filters"])
    return text + "."


def answer(question: str, k: int = TOP_K) -> dict:
    """Answer a question. Returns the contract-3 fields:
    sql, columns, rows, route, explanation, attempts, latency_ms.
    Raises UnsupportedQuestion or QueryFailed when it can't answer."""
    engine = _engine
    if engine is None:
        raise RuntimeError("engine not configured; call configure() first")
    generator = _generator(engine, question)
    strategy = os.getenv("SCHOLARQL_STRATEGY", "few_shot_correction")
    if _is_topic(question):
        out = engine.search(question, "semantic", "local", strategy, k)
    else:
        out = engine.search(question, "auto", generator, strategy, k)

    def failed(o: dict) -> bool:
        return o["status"] in ("error", "unsupported") and o["route"] == "sql"

    if failed(out) and generator != "local":
        # The LLM failed (quota, timeout, bad SQL): try the other LLM, then the compiler
        for other in [g for g in _llms(engine) if g != generator]:
            out = engine.search(question, "auto", other, strategy, k)
            if not failed(out):
                break
        if failed(out) and compile_question(question):
            out = engine.search(question, "auto", "local", strategy, k)
    if failed(out) and not EXACT_WORDS.search(question):
        # Not a structural question after all: answer it by meaning
        out = engine.search(question, "semantic", "local", strategy, k)

    if out["status"] == "unsupported":
        raise UnsupportedQuestion(out["diagnostic"] or "The engine can't answer this question.")
    if out["status"] == "error":
        if (out["diagnostic"] or "").startswith(MONGO_DOWN):
            raise DocumentsUnavailable(out["diagnostic"])
        raise QueryFailed(out["diagnostic"] or "The query failed.")

    if out["route"] == "sql":
        columns = list(out["columns"])
        rows = [_jsonable(list(r)) for r in out["rows"]]
        sql = out["sql"] or None
    else:
        columns = ["paper_id", "title", "year", "score"]
        rows = [
            [p["paper_id"], p["title"], p["publication_year"], p["score"]] for p in out["papers"]
        ]
        # The filter SQL is part of a hybrid answer; a purely semantic one has none
        sql = out["sql"] if out["route"] == "hybrid" else None

    return {
        "sql": sql,
        "columns": columns,
        "rows": rows,
        "route": out["route"],
        "explanation": _explanation(out),
        "attempts": max(len(out.get("attempts") or []), 1),
        "latency_ms": round(out["latency_ms"]),
    }
