"""Apply the supplied PostgreSQL migration and seed PostgreSQL or MongoDB."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

import psycopg
from psycopg import sql
from pymongo import MongoClient, UpdateOne
from pymongo.operations import SearchIndexModel
from scholarql.config import PILOT, ROOT
from scholarql.db import READ_TABLES, populate, read_pilot
from scholarql.retrieval import MiniLM, TextIndex, load_documents, model_directory

MIGRATION = ROOT.parent / "db/migrations/20261125000100_initial_schema.sql"


def ensure_schema(connection):
    present = connection.execute("SELECT to_regclass('public.paper')").fetchone()[0]
    if present is None:
        connection.execute(
            MIGRATION.read_text(encoding="utf-8").split("-- migrate:down")[0], prepare=False
        )


def set_reader(connection, password):
    found = connection.execute(
        "SELECT 1 FROM pg_roles WHERE rolname = 'scholarql_reader'"
    ).fetchone()
    command = "ALTER ROLE" if found else "CREATE ROLE"
    connection.execute(
        sql.SQL(command + " scholarql_reader LOGIN PASSWORD {}").format(sql.Literal(password))
    )
    connection.execute("ALTER ROLE scholarql_reader SET default_transaction_read_only = on")
    connection.execute("ALTER ROLE scholarql_reader SET statement_timeout = '3500ms'")
    connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    connection.execute("GRANT USAGE ON SCHEMA public TO scholarql_reader")
    tables = sql.SQL(", ").join(sql.Identifier("public", table) for table in sorted(READ_TABLES))
    connection.execute(sql.SQL("GRANT SELECT ON {} TO scholarql_reader").format(tables))
    connection.execute("REVOKE EXECUTE ON PROCEDURE refresh_analytics() FROM PUBLIC")
    connection.execute(
        "REVOKE EXECUTE ON PROCEDURE compute_pagerank(integer, double precision) FROM PUBLIC"
    )


def seed_postgres(dsn, fixture, password):
    with psycopg.connect(dsn) as conn:
        # Prevent concurrent initializers from loading the same snapshot.
        conn.execute("SELECT pg_advisory_xact_lock(2026112501)")
        ensure_schema(conn)
        if fixture:
            digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
            conn.execute("CREATE TABLE IF NOT EXISTS scholarql_snapshot (digest text PRIMARY KEY)")
            existing = conn.execute("SELECT digest FROM scholarql_snapshot").fetchall()
            if existing != [(digest,)]:
                if existing or conn.execute("SELECT EXISTS (SELECT 1 FROM paper)").fetchone()[0]:
                    raise ValueError(
                        "Use an empty ScholarQL PostgreSQL database to install this snapshot."
                    )
                populate(conn, read_pilot(fixture)["entities"], postgres=True)
                conn.execute("CALL compute_pagerank()")
                conn.execute("CALL refresh_analytics()")
                conn.execute("INSERT INTO scholarql_snapshot VALUES (%s)", (digest,))
                conn.execute("ANALYZE")
        if password:
            set_reader(conn, password)
        print("PostgreSQL papers:", conn.execute("SELECT count(*) FROM paper").fetchone()[0])


def seed_mongo(uri, db_name, fixture, dense, atlas_index):
    documents = load_documents(fixture)
    if dense:
        index = TextIndex(documents, MiniLM(model_directory()))
        documents = [
            {**item, "embedding": vector.tolist()}
            for item, vector in zip(index.documents, index.embeddings())
        ]
        for item in documents:
            item["embedding_model"] = index.encoder.fingerprint
    with MongoClient(uri, serverSelectionTimeoutMS=5000) as client:
        coll = client[db_name].paper_documents
        coll.create_index("paper_id", unique=True)
        for start in range(0, len(documents), 500):
            batch = documents[start : start + 500]
            requests = []
            for item in batch:
                update = {"$set": item}
                if not dense:
                    update["$unset"] = {"embedding": "", "embedding_model": ""}
                requests.append(UpdateOne({"paper_id": item["paper_id"]}, update, upsert=True))
            if requests:
                coll.bulk_write(requests, ordered=False)
        client[db_name].query_logs.create_index("created_at")
        if atlas_index:
            if not dense:
                raise ValueError("--atlas-index requires --dense.")
            if not any(entry["name"] == atlas_index for entry in coll.list_search_indexes()):
                coll.create_search_index(
                    SearchIndexModel(
                        name=atlas_index,
                        type="vectorSearch",
                        definition={
                            "fields": [
                                {
                                    "type": "vector",
                                    "path": "embedding",
                                    "numDimensions": 384,
                                    "similarity": "cosine",
                                },
                                {"type": "filter", "path": "paper_id"},
                            ]
                        },
                    )
                )
            print("Check search-index readiness before querying Atlas.")
        print("MongoDB documents upserted:", len(documents))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=["postgres", "mongo", "both"])
    parser.add_argument("--fixture", type=Path, default=PILOT)
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Apply the relational migration without seeding papers.",
    )
    parser.add_argument("--dense", action="store_true")
    parser.add_argument("--atlas-index")
    args = parser.parse_args()
    if args.atlas_index and not args.dense:
        parser.error("--atlas-index requires --dense")
    if args.target in {"postgres", "both"}:
        dsn = os.getenv("DATABASE_URL")
        if not dsn:
            parser.error("Set DATABASE_URL to the PostgreSQL owner connection.")
        seed_postgres(
            dsn, None if args.schema_only else args.fixture, os.getenv("SCHOLARQL_READER_PASSWORD")
        )
    if args.target in {"mongo", "both"} and not args.schema_only:
        uri = os.getenv("MONGODB_URI")
        if not uri:
            parser.error("Set MONGODB_URI.")
        seed_mongo(
            uri,
            os.getenv("MONGODB_DATABASE", "scholarql"),
            args.fixture,
            args.dense,
            args.atlas_index,
        )


if __name__ == "__main__":
    main()
