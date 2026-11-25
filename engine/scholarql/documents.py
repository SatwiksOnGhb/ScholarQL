"""Document storage, optional Atlas search, and query-level evidence logging."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from .config import PILOT, RUNTIME
from .retrieval import TextIndex, load_documents


class DocumentStore:
    def __init__(self, local_path: Path | None, mongo_uri: str = "", db_name: str = "scholarql"):
        self.name = "MongoDB" if mongo_uri else "Local snapshot"
        self.atlas_index = os.getenv("MONGODB_VECTOR_INDEX", "") if mongo_uri else ""
        self.client = (
            MongoClient(mongo_uri, serverSelectionTimeoutMS=2500, socketTimeoutMS=5000)
            if mongo_uri
            else None
        )
        self.mongo = self.client[db_name] if self.client is not None else None
        self.local_path = local_path
        self.local = (
            {item["paper_id"]: item for item in load_documents(local_path)}
            if self.mongo is None and local_path
            else {}
        )
        self.log_path = RUNTIME / "history.sqlite"
        self.logging = os.getenv("SCHOLARQL_LOG_QUERIES", "1") != "0"

    @classmethod
    def from_environment(cls, postgres: bool):
        path = os.getenv("SCHOLARQL_CONTENT_PATH")
        label = os.getenv("SCHOLARQL_CORPUS_LABEL", "")
        return cls(
            Path(path)
            if path
            else PILOT
            if not postgres or label == "arXiv research pilot"
            else None,
            os.getenv("MONGODB_URI", ""),
            os.getenv("MONGODB_DATABASE", "scholarql"),
        )

    def close(self):
        if self.client is not None:
            self.client.close()

    def all(self) -> list[dict]:
        if self.mongo is None:
            return list(self.local.values())
        documents = list(
            self.mongo.paper_documents.find({}, {"_id": 0, "embedding": 0}).limit(100_001)
        )
        if len(documents) > 100_000:
            raise ValueError(
                "Use a dedicated search index for document collections larger than 100,000 records."
            )
        return documents

    def get(self, paper_id: str) -> dict:
        if self.mongo is None:
            return self.local.get(paper_id, {})
        return (
            self.mongo.paper_documents.find_one({"paper_id": paper_id}, {"_id": 0, "embedding": 0})
            or {}
        )

    def atlas_rank(
        self, index: TextIndex, concept: str, eligible: set[str] | None, k: int
    ) -> list[dict]:
        if eligible is not None and not eligible:
            return []
        # For large allowlists, use exact CPU cosine over the same authorized IDs.
        if eligible is not None and len(eligible) > 1500:
            return index.rank(concept, eligible=eligible, k=k, mode="minilm")
        query = {
            "index": self.atlas_index,
            "path": "embedding",
            "queryVector": index.encoder.encode([concept])[0].tolist(),
            "exact": True,
            "limit": k,
        }
        if eligible is not None:
            query["filter"] = {"paper_id": {"$in": sorted(eligible)}}
        cursor = self.mongo.paper_documents.aggregate(
            [
                {"$vectorSearch": query},
                {"$project": {"_id": 0, "paper_id": 1, "score": {"$meta": "vectorSearchScore"}}},
            ],
            maxTimeMS=4000,
        )
        return list(cursor)

    def save_log(self, event: dict) -> bool:
        if not self.logging:
            return False
        record = {"created_at": datetime.now(UTC).isoformat(), **event}
        try:
            if self.mongo is not None:
                self.mongo.query_logs.insert_one(record)
            else:
                with self._local_logs() as log:
                    log.execute(
                        "INSERT INTO query_log (record) VALUES (?)",
                        (json.dumps(record, ensure_ascii=False),),
                    )
        except (PyMongoError, sqlite3.Error, OSError):
            return False
        return True

    def get_logs(self, cap: int = 30) -> list[dict]:
        if not self.logging:
            return []
        if self.mongo is not None:
            return list(self.mongo.query_logs.find({}, {"_id": 0}).sort("_id", -1).limit(cap))
        with self._local_logs() as log:
            rows = log.execute(
                "SELECT record FROM query_log ORDER BY id DESC LIMIT ?", (cap,)
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def _local_logs(self):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.log_path, timeout=2, factory=ClosingConnection)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS query_log (id INTEGER PRIMARY KEY, record TEXT NOT NULL)"
        )
        return conn


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()
