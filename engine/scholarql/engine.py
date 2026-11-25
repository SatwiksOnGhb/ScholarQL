"""Connect routing, SQL execution, document ranking, and provenance."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from threading import Lock
from time import perf_counter

from pymongo.errors import PyMongoError

from .db import DB_ERRORS, Database, QueryRows
from .documents import DocumentStore
from .intents import (
    compile_question,
    extract_filters,
    route_question,
    unresolved_constraints,
    unsupported_filter_logic,
)
from .providers import Provider, ProviderError, Strategy
from .retrieval import MiniLM, TextIndex, model_directory
from .safety import QueryError, validate_sql

FILTER_CAP = 100_000
RANK_NAMES = {"minilm": "MiniLM cosine", "tfidf": "TF-IDF cosine", "bm25": "BM25"}


@dataclass
class SQLAttempt:
    sql: str = ""
    result: QueryRows | None = None
    attempts: list[dict] = field(default_factory=list)
    error: str = ""
    planner_checked: bool = False


def execute_generated(
    database: Database,
    question: str,
    provider: Provider,
    strategy: Strategy,
    *,
    cap: int = 100,
    projection: list[str] | None = None,
) -> SQLAttempt:
    output = SQLAttempt()
    for index in range(2 if strategy == "few_shot_correction" else 1):
        try:
            candidate = provider.generate(
                question,
                strategy,
                database.engine,
                feedback=output.error or None,
                previous=output.sql,
                projection=projection,
            )
        except ProviderError as error:
            output.error = str(error)
            output.attempts.append({"status": "provider_error", "diagnostic": output.error})
            break
        output.sql = candidate[:12_000] if isinstance(candidate, str) else ""
        try:
            output.sql = validate_sql(candidate if isinstance(candidate, str) else "")
            output.result = database.run(output.sql, cap=cap, explain=True)
        except (QueryError, *DB_ERRORS) as error:
            output.error = Database.explain_error(error)[:350]
            output.attempts.append({"status": "rejected", "diagnostic": output.error})
            continue
        output.error = ""
        output.planner_checked = database.postgres
        output.attempts.append({"status": "executed"})
        break
    return output


class SearchEngine:
    def __init__(self, database: Database, documents: DocumentStore, retrieval: str = "tfidf"):
        if retrieval not in RANK_NAMES:
            raise ValueError("SCHOLARQL_RETRIEVAL must be tfidf, bm25, or minilm.")
        if documents.atlas_index and retrieval != "minilm":
            raise ValueError("MongoDB Vector Search requires SCHOLARQL_RETRIEVAL=minilm.")
        self.db = database
        self.documents = documents
        self.retrieval = retrieval
        self.providers = Provider.configured()
        self._index = None
        self._lock = Lock()

    @classmethod
    def from_environment(cls):
        db = Database.from_environment()
        return cls(
            db,
            DocumentStore.from_environment(db.postgres),
            os.getenv("SCHOLARQL_RETRIEVAL", "tfidf").lower(),
        )

    def index(self) -> TextIndex:
        with self._lock:
            if self._index is None:
                encoder = MiniLM(model_directory()) if self.retrieval == "minilm" else None
                self._index = TextIndex(self.documents.all(), encoder)
        return self._index

    def search(self, question: str, mode: str, generator: str, strategy: Strategy, k: int) -> dict:
        started = perf_counter()
        local_sql = compile_question(question)
        filters = extract_filters(question)
        route = route_question(question, filters, local_sql) if mode == "auto" else mode
        # Document search always applies any explicit metadata constraint.
        if route == "semantic" and filters.conditions:
            route = "hybrid"
        output = {
            "question": question,
            "route": route,
            "status": "answered",
            "generator": generator,
            "strategy": strategy if generator != "local" else None,
            "sql": "",
            "sql_engine": self.db.engine,
            "attempts": [],
            "planner_checked": False,
            "columns": [],
            "rows": [],
            "papers": [],
            "truncated": False,
            "filters": [],
            "candidates": None,
            "diagnostic": "",
        }
        try:
            if route == "sql":
                self._relational(output, question, generator, strategy, local_sql)
            else:
                self._rank(output, filters, k)
        except (QueryError, ValueError, ImportError, PyMongoError, *DB_ERRORS) as err:
            output.update(
                status="error",
                diagnostic=(
                    "The document database is unavailable. Check its connection and index."
                    if isinstance(err, PyMongoError)
                    else Database.explain_error(err)[:350]
                ),
            )
        output["latency_ms"] = round((perf_counter() - started) * 1000, 2)
        output["logged"] = self.documents.save_log(
            {
                key: output[key]
                for key in (
                    "question",
                    "route",
                    "generator",
                    "strategy",
                    "sql",
                    "status",
                    "latency_ms",
                )
            }
        )
        return output

    def _relational(self, output, question, generator, strategy, local_sql):
        if generator == "local":
            if not local_sql:
                output.update(
                    status="unsupported",
                    diagnostic=(
                        "This question is outside the local query patterns. Try a suggested query, or select a configured model."
                    ),
                )
                return
            output["sql"] = validate_sql(local_sql)
            result = self.db.run(output["sql"], explain=True)
            output.update(attempts=[{"status": "executed"}], planner_checked=self.db.postgres)
        else:
            provider = self.providers.get(generator)
            if not provider:
                output.update(
                    status="unsupported",
                    diagnostic=f"Configure the {generator.title()} key and model, then restart ScholarQL.",
                )
                return
            attempt = execute_generated(self.db, question, provider, strategy)
            output.update(
                sql=attempt.sql,
                attempts=attempt.attempts,
                planner_checked=attempt.planner_checked,
                model=provider.model,
            )
            if attempt.result is None:
                output.update(status="error", diagnostic=attempt.error)
                return
            result = attempt.result
        output.update(
            status="answered" if result.rows else "no_results",
            columns=result.columns,
            rows=result.rows,
            truncated=result.truncated,
        )

    def _rank(self, output, filters, k):
        if unresolved_constraints(filters.concept) or unsupported_filter_logic(output["question"]):
            output.update(
                status="unsupported",
                diagnostic=(
                    'Use an explicit filter such as “since 2021”, “tagged "cs.LG"”, or “at "arXiv"” with a research concept.'
                ),
            )
            return
        if not filters.concept or not filters.concept.strip(" ,&"):
            output.update(
                status="unsupported",
                diagnostic="Add a research concept to rank the matching papers.",
            )
            return
        output.update(sql=filters.sql, filters=filters.labels)
        rows = self.db.run(filters.sql, cap=FILTER_CAP)
        if rows.truncated:
            raise QueryError(
                "The candidate set exceeds 100,000 papers. Add a year, topic, or venue filter."
            )
        eligible = {row[0] for row in rows.rows}
        output["candidates"] = len(eligible)
        index = self.index()
        if not index.documents:
            output.update(
                status="unsupported",
                diagnostic="Load research documents or configure MongoDB before using document search.",
            )
            return
        atlas = bool(self.documents.atlas_index) and len(eligible) <= 1500
        output.update(
            retriever="MongoDB Vector Search" if atlas else RANK_NAMES[self.retrieval],
            concept=filters.concept,
            documents_in_scope=len(eligible.intersection(index.positions)),
        )
        ranking = (
            self.documents.atlas_rank(index, filters.concept, eligible, k)
            if atlas
            else index.rank(filters.concept, eligible=eligible, k=k, mode=self.retrieval)
        )
        papers = []
        for rank in ranking:
            pid = rank["paper_id"]
            if pid not in eligible or pid not in index.positions:
                continue
            document = index.documents[index.positions[pid]]
            papers.append({**document, "score": round(rank["score"], 5)})
        output.update(papers=papers, status="answered" if papers else "no_results")
