"""Query logging: one MongoDB query_logs document per question asked, plus user feedback.

The document shape is enforced by the $jsonSchema in mongo/init/01-collections.js.
The analytics page (task 11) aggregates over these documents.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from pymongo.errors import PyMongoError

from app.db import mongo
from app.errors import ApiError
from app.models.ask import Answer, Route

log = logging.getLogger(__name__)


def build_log_doc(
    question: str,
    answer: Answer | None,
    *,
    latency_ms: int,
    error: str | None = None,
    route: Route = "sql",
    now: datetime | None = None,
) -> dict[str, Any]:
    """The query_logs document for one question. `answer` is None when the engine failed;
    `route` is only used then (the answer carries its own route otherwise)."""
    doc: dict[str, Any] = {
        "question": question,
        "sql": answer.sql if answer else None,
        "route": answer.route if answer else route,
        "ok": answer is not None and error is None,
        "latency_ms": latency_ms,
        "error": error,
        "feedback": None,
        "created_at": now or datetime.now(UTC),
    }
    if answer:  # extra fields; allowed by the validator, useful for analytics
        doc["attempts"] = answer.attempts
        doc["row_count"] = len(answer.rows)
    return doc


async def log_query(
    question: str,
    answer: Answer | None,
    *,
    latency_ms: int,
    error: str | None = None,
    route: Route = "sql",
) -> str | None:
    """Store the question and its outcome; return the log ID (the `query_id` sent to clients).

    Never raises: if MongoDB is unavailable the answer still goes out, just without an ID.
    """
    doc = build_log_doc(question, answer, latency_ms=latency_ms, error=error, route=route)
    try:
        result = await mongo.get_db().query_logs.insert_one(doc)
        return str(result.inserted_id)
    except PyMongoError as exc:
        log.warning("could not log query: %s", exc)
        return None


async def record_feedback(query_id: str, correct: bool, comment: str | None) -> None:
    """Attach (or replace) the user's verdict on a logged answer."""
    feedback = {"correct": correct, "comment": comment, "created_at": datetime.now(UTC)}
    try:
        result = await mongo.get_db().query_logs.update_one(
            {"_id": ObjectId(query_id)}, {"$set": {"feedback": feedback}}
        )
    except PyMongoError as exc:
        log.warning("could not store feedback: %s", exc)
        raise ApiError(503, "service_unavailable", "Feedback can't be saved right now") from exc
    if result.matched_count == 0:
        raise ApiError(404, "not_found", f"No logged query with id {query_id}")
