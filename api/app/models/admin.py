"""Shapes for GET /admin/stats (aggregation pipelines over MongoDB query_logs)."""

from pydantic import BaseModel, Field

from app.models.ask import Route


class RouteWeekAccuracy(BaseModel):
    week: str = Field(description="ISO week, e.g. 2026-W43")
    route: Route
    total: int
    correct: int
    accuracy: float | None = Field(description="correct / answers with feedback; null if none")


class RouteLatency(BaseModel):
    route: Route
    count: int
    p50_ms: float
    p95_ms: float


class QuestionCount(BaseModel):
    question: str
    count: int


class FailureReason(BaseModel):
    reason: str
    count: int


class AdminStats(BaseModel):
    total_queries: int
    accuracy: float | None
    p95_latency_ms: float
    accuracy_by_route_week: list[RouteWeekAccuracy]
    latency_by_route: list[RouteLatency]
    top_questions: list[QuestionCount]
    failure_reasons: list[FailureReason]
