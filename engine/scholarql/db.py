"""Read-only connections and installation of the frozen portable pilot."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

import psycopg

from .config import PILOT, ROOT, RUNTIME

PILOT_SCHEMA = ROOT / "db/pilot_sqlite.sql"
COLUMNS = {
    "institution": ("institution_id", "name", "country_code"),
    "venue": ("venue_id", "name", "venue_type"),
    "author": ("author_id", "name"),
    "topic": ("topic_id", "name", "parent_topic_id", "level"),
    "paper": (
        "paper_id",
        "title",
        "publication_year",
        "publication_date",
        "arxiv_id",
        "doi",
        "venue_id",
    ),
    "authorship": ("paper_id", "author_id", "author_order"),
    "author_affiliation": ("paper_id", "author_id", "institution_id"),
    "paper_topic": ("paper_id", "topic_id", "relevance", "is_primary"),
    "citation": ("citing_id", "cited_id", "source"),
}
READ_TABLES = frozenset(COLUMNS) | {"topic_year_trends", "author_stats"}


def read_pilot(path: Path = PILOT) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def populate(connection, entities: dict, postgres: bool = False) -> None:
    placeholder = "%s" if postgres else "?"
    with connection.cursor() if postgres else _sqlite_cursor(connection) as cur:
        for table, columns in COLUMNS.items():
            fields = ", ".join(columns)
            values = ", ".join([placeholder] * len(columns))
            cur.executemany(f"INSERT INTO {table} ({fields}) VALUES ({values})", entities[table])


@contextmanager
def _sqlite_cursor(connection):
    cur = connection.cursor()
    try:
        yield cur
    finally:
        cur.close()


def install_pilot(fixture: Path = PILOT, directory: Path = RUNTIME) -> Path:
    data = fixture.read_bytes()
    schema = PILOT_SCHEMA.read_bytes()
    digest = hashlib.sha256(data + schema).hexdigest()[:16]
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"pilot-{digest}.sqlite"
    if target.exists():
        return target
    with tempfile.NamedTemporaryFile(dir=directory, suffix=".sqlite", delete=False) as tmp:
        staging = Path(tmp.name)
    try:
        with sqlite3.connect(staging) as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript(schema.decode())
            populate(conn, json.loads(data)["entities"])
            conn.commit()
            conn.execute("ANALYZE")
            conn.commit()
        conn.close()
        try:
            staging.replace(target)
        except PermissionError:
            if not target.exists():
                raise
    finally:
        staging.unlink(missing_ok=True)
    return target


@dataclass
class QueryRows:
    columns: list[str]
    rows: list[tuple]
    truncated: bool = False

    def records(self) -> list[dict]:
        return [dict(zip(self.columns, row)) for row in self.rows]


class Database:
    def __init__(self, dsn: str = "", path: Path | None = None):
        self.dsn = dsn
        self.path = path or (install_pilot() if not dsn else None)
        self.postgres = bool(dsn)
        self.engine = "PostgreSQL" if self.postgres else "SQLite"

    @classmethod
    def from_environment(cls):
        return cls(os.getenv("SCHOLARQL_DATABASE_URL", ""))

    @contextmanager
    def connect(self):
        if self.postgres:
            with psycopg.connect(self.dsn, connect_timeout=5) as conn:
                conn.execute("SET TRANSACTION READ ONLY")
                conn.execute("SET LOCAL statement_timeout = '3500ms'")
                conn.execute("SET LOCAL lock_timeout = '1000ms'")
                conn.execute("SET LOCAL search_path TO pg_catalog, public")
                yield conn
            return
        conn = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            deadline = monotonic() + 3.5
            conn.set_progress_handler(lambda: monotonic() > deadline, 10_000)
            conn.execute("PRAGMA query_only=ON")
            conn.create_function(
                "strpos",
                2,
                lambda a, b: a.find(b) + 1 if a is not None and b is not None else None,
                deterministic=True,
            )
            yield conn
        finally:
            conn.close()

    def run(
        self, sql: str, parameters: tuple = (), *, cap: int = 100, explain: bool = False
    ) -> QueryRows:
        with self.connect() as conn:
            if self.postgres and parameters:
                sql = sql.replace("?", "%s")
            if self.postgres and explain:
                conn.execute("EXPLAIN (FORMAT JSON) " + sql, parameters or None).fetchone()
            cursor = (
                conn.execute(sql, parameters or None)
                if self.postgres
                else conn.execute(sql, parameters)
            )
            rows = cursor.fetchmany(cap + 1)
            columns = [item[0] for item in cursor.description]
        return QueryRows(columns, rows[:cap], len(rows) > cap)

    def count(self, table: str) -> int:
        if table not in READ_TABLES:
            raise ValueError("Unknown table")
        return self.run(f"SELECT count(*) FROM {table}").rows[0][0]

    @staticmethod
    def explain_error(error: Exception) -> str:
        if isinstance(error, psycopg.Error):
            return error.diag.message_primary or "PostgreSQL could not execute the query."
        return str(error)


DB_ERRORS = (sqlite3.Error, psycopg.Error)
