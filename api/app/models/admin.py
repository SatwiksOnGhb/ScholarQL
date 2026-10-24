"""Shapes for GET /admin/stats (aggregation pipelines over MongoDB query_logs)."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.ask import Route


class RouteWeekAccuracy(BaseModel):
    week: str = Field(description="ISO week, e.g. 2026-W43")
    route: Route
    total: int
    with_feedback: int
    correct: int
    accuracy: float | None = Field(description="correct / with_feedback; null if no feedback")


class RouteLatency(BaseModel):
    route: Route
    count: int
    p50_ms: float
    p95_ms: float


class QuestionCount(BaseModel):
    question: str
    count: int


class FailureReason(BaseModel):
    reason: str = Field(description="Error type, e.g. TimeoutError")
    count: int


class AdminStats(BaseModel):
    since: datetime = Field(description="Start of the window (UTC)")
    weeks: int
    total_queries: int
    failed_queries: int
    failure_rate: float | None
    with_feedback: int
    accuracy: float | None = Field(description="Share of rated answers marked correct")
    p95_latency_ms: float | None
    accuracy_by_route_week: list[RouteWeekAccuracy]
    latency_by_route: list[RouteLatency]
    top_questions: list[QuestionCount]
    failure_reasons: list[FailureReason]
