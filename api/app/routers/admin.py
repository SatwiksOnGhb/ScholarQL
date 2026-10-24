"""Usage analytics. Owned by Person C.

PLACEHOLDER: fixed numbers. Task 11 replaces this with aggregation pipelines over query_logs.
"""

from fastapi import APIRouter

from app.models.admin import (
    AdminStats,
    FailureReason,
    QuestionCount,
    RouteLatency,
    RouteWeekAccuracy,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats")
async def get_stats() -> AdminStats:
    weekly = []
    for i, week in enumerate(["2026-W41", "2026-W42", "2026-W43"]):
        for route, base in (("sql", 0.62), ("semantic", 0.70), ("hybrid", 0.55)):
            total = 40 + 10 * i
            correct = round(total * (base + 0.05 * i))
            weekly.append(
                RouteWeekAccuracy(
                    week=week,
                    route=route,
                    total=total,
                    correct=correct,
                    accuracy=round(correct / total, 3),
                )
            )
    return AdminStats(
        total_queries=sum(w.total for w in weekly),
        accuracy=round(sum(w.correct for w in weekly) / sum(w.total for w in weekly), 3),
        p95_latency_ms=4200.0,
        accuracy_by_route_week=weekly,
        latency_by_route=[
            RouteLatency(route="sql", count=150, p50_ms=1800.0, p95_ms=4200.0),
            RouteLatency(route="semantic", count=150, p50_ms=350.0, p95_ms=900.0),
            RouteLatency(route="hybrid", count=150, p50_ms=2500.0, p95_ms=5600.0),
        ],
        top_questions=[
            QuestionCount(question="Top 10 venues by average citations since 2020", count=14),
            QuestionCount(question="Papers by Pieter Abbeel in 2021", count=9),
            QuestionCount(question="Papers about diffusion models", count=7),
        ],
        failure_reasons=[
            FailureReason(reason="sql_error_after_retries", count=11),
            FailureReason(reason="empty_result", count=8),
            FailureReason(reason="timeout", count=3),
        ],
    )
