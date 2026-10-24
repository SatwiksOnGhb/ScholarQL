"""Usage analytics over query_logs, computed by one MongoDB aggregation.

$match narrows to the time window once; $facet then runs five sub-pipelines over the same
documents in a single round trip. The created_at index (mongo/init) serves the $match.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo.errors import PyMongoError

from app.db import mongo
from app.errors import ApiError
from app.models.admin import (
    AdminStats,
    FailureReason,
    QuestionCount,
    RouteLatency,
    RouteWeekAccuracy,
)

log = logging.getLogger(__name__)

TOP_N = 10
# $percentile (MongoDB 7.0+); "approximate" is the only method MongoDB supports
P50_P95 = {"$percentile": {"input": "$latency_ms", "p": [0.5, 0.95], "method": "approximate"}}
IS_CORRECT = {"$cond": [{"$eq": ["$feedback.correct", True]}, 1, 0]}
ISO_WEEK = {"$dateToString": {"format": "%G-W%V", "date": "$created_at"}}  # e.g. 2026-W43
HAS_FEEDBACK = {"$cond": [{"$eq": [{"$type": "$feedback"}, "object"]}, 1, 0]}


def stats_pipeline(since: datetime) -> list[dict[str, Any]]:
    return [
        {"$match": {"created_at": {"$gte": since}}},
        {
            "$facet": {
                "overall": [
                    {
                        "$group": {
                            "_id": None,
                            "total": {"$sum": 1},
                            "failed": {"$sum": {"$cond": ["$ok", 0, 1]}},
                            # Fake logs from jobs/seed; the page warns when any are present
                            "seeded": {"$sum": {"$cond": [{"$eq": ["$seed", True]}, 1, 0]}},
                            "with_feedback": {"$sum": HAS_FEEDBACK},
                            "correct": {"$sum": IS_CORRECT},
                            "latency": P50_P95,
                        }
                    }
                ],
                "by_route_week": [
                    {
                        "$group": {
                            "_id": {"week": ISO_WEEK, "route": "$route"},
                            "total": {"$sum": 1},
                            "with_feedback": {"$sum": HAS_FEEDBACK},
                            "correct": {"$sum": IS_CORRECT},
                        }
                    },
                    {"$sort": {"_id.week": 1, "_id.route": 1}},
                ],
                "latency_by_route": [
                    {"$group": {"_id": "$route", "count": {"$sum": 1}, "latency": P50_P95}},
                    {"$sort": {"_id": 1}},
                ],
                "top_questions": [
                    # Group case- and whitespace-insensitively; show the first spelling seen
                    {
                        "$group": {
                            "_id": {"$toLower": {"$trim": {"input": "$question"}}},
                            "question": {"$first": "$question"},
                            "count": {"$sum": 1},
                        }
                    },
                    {"$sort": {"count": -1, "_id": 1}},
                    {"$limit": TOP_N},
                ],
                "failure_reasons": [
                    {"$match": {"ok": False}},
                    {
                        # "TimeoutError: statement timeout" -> "TimeoutError"
                        "$group": {
                            "_id": {
                                "$trim": {
                                    "input": {
                                        "$arrayElemAt": [
                                            {"$split": [{"$ifNull": ["$error", "Unknown"]}, ":"]},
                                            0,
                                        ]
                                    }
                                }
                            },
                            "count": {"$sum": 1},
                        }
                    },
                    {"$sort": {"count": -1, "_id": 1}},
                ],
            }
        },
    ]


def _ratio(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def shape_stats(facets: dict[str, list[dict]], since: datetime, weeks: int) -> AdminStats:
    """Turn the $facet output into the API response."""
    overall = (facets.get("overall") or [{}])[0]
    total = overall.get("total", 0)
    with_feedback = overall.get("with_feedback", 0)
    latency = overall.get("latency")
    return AdminStats(
        since=since,
        weeks=weeks,
        total_queries=total,
        seeded_queries=overall.get("seeded", 0),
        failed_queries=overall.get("failed", 0),
        failure_rate=_ratio(overall.get("failed", 0), total),
        with_feedback=with_feedback,
        accuracy=_ratio(overall.get("correct", 0), with_feedback),
        p95_latency_ms=round(latency[1], 1) if latency else None,
        accuracy_by_route_week=[
            RouteWeekAccuracy(
                week=d["_id"]["week"],
                route=d["_id"]["route"],
                total=d["total"],
                with_feedback=d["with_feedback"],
                correct=d["correct"],
                accuracy=_ratio(d["correct"], d["with_feedback"]),
            )
            for d in facets.get("by_route_week", [])
        ],
        latency_by_route=[
            RouteLatency(
                route=d["_id"],
                count=d["count"],
                p50_ms=round(d["latency"][0], 1),
                p95_ms=round(d["latency"][1], 1),
            )
            for d in facets.get("latency_by_route", [])
        ],
        top_questions=[
            QuestionCount(question=d["question"], count=d["count"])
            for d in facets.get("top_questions", [])
        ],
        failure_reasons=[
            FailureReason(reason=d["_id"] or "Unknown", count=d["count"])
            for d in facets.get("failure_reasons", [])
        ],
    )


def window_start(weeks: int, now: datetime | None = None) -> datetime:
    """Monday 00:00 UTC of the first week, so the window is `weeks` whole ISO weeks
    (the current, partial week included) and no week is cut in half at the start."""
    today = (now or datetime.now(UTC)).replace(hour=0, minute=0, second=0, microsecond=0)
    this_monday = today - timedelta(days=today.weekday())
    return this_monday - timedelta(weeks=weeks - 1)


async def get_stats(weeks: int) -> AdminStats:
    since = window_start(weeks)
    try:
        cursor = await mongo.get_db().query_logs.aggregate(stats_pipeline(since))
        facets = await cursor.next()
    except PyMongoError as exc:
        log.warning("analytics aggregation failed: %s", exc)
        raise ApiError(503, "service_unavailable", "Analytics are unavailable right now") from exc
    return shape_stats(facets, since, weeks)
