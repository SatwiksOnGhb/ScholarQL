"""Tests for /admin/stats. The aggregation itself was checked against the real database;
here we test the window maths, the response shaping and the endpoint (MongoDB faked)."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import admin as admin_router
from app.services.analytics import shape_stats, window_start

SINCE = datetime(2026, 8, 31, tzinfo=UTC)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_window_starts_on_monday_and_spans_whole_weeks():
    saturday = datetime(2026, 10, 24, 15, 30, tzinfo=UTC)
    assert window_start(1, saturday) == datetime(2026, 10, 19, tzinfo=UTC)  # this Monday
    assert window_start(8, saturday) == SINCE  # 7 full weeks before it
    monday = datetime(2026, 10, 19, 0, 5, tzinfo=UTC)
    assert window_start(1, monday) == datetime(2026, 10, 19, tzinfo=UTC)


def _cell(route: str, total: int, rated: int, correct: int) -> dict:
    week = {"week": "2026-W43", "route": route}
    return {"_id": week, "total": total, "with_feedback": rated, "correct": correct}


def test_shape_stats_from_facets():
    facets = {
        "overall": [
            {"total": 10, "failed": 2, "with_feedback": 4, "correct": 3, "latency": [100.0, 900.0]}
        ],
        "by_route_week": [_cell("sql", 6, 4, 3), _cell("hybrid", 4, 0, 0)],
        "latency_by_route": [{"_id": "sql", "count": 6, "latency": [120.04, 880.06]}],
        "top_questions": [{"question": "Q?", "count": 7}],
        "failure_reasons": [{"_id": "TimeoutError", "count": 2}],
    }
    s = shape_stats(facets, SINCE, 8)
    assert (s.total_queries, s.failed_queries, s.failure_rate) == (10, 2, 0.2)
    assert (s.with_feedback, s.accuracy, s.p95_latency_ms) == (4, 0.75, 900.0)
    assert s.accuracy_by_route_week[0].accuracy == 0.75
    assert s.accuracy_by_route_week[1].accuracy is None  # no feedback that week
    assert (s.latency_by_route[0].p50_ms, s.latency_by_route[0].p95_ms) == (120.0, 880.1)
    assert s.failure_reasons[0].reason == "TimeoutError"


def test_shape_stats_empty_database():
    empty = {
        k: []
        for k in (
            "overall",
            "by_route_week",
            "latency_by_route",
            "top_questions",
            "failure_reasons",
        )
    }
    s = shape_stats(empty, SINCE, 8)
    assert s.total_queries == 0
    assert s.accuracy is None and s.failure_rate is None and s.p95_latency_ms is None


def test_stats_endpoint(client, monkeypatch):
    seen = []

    async def fake_get_stats(weeks):
        seen.append(weeks)
        return shape_stats({}, SINCE, weeks)

    monkeypatch.setattr(admin_router, "get_stats", fake_get_stats)
    assert client.get("/admin/stats", params={"weeks": 4}).json()["weeks"] == 4
    assert seen == [4]
    assert client.get("/admin/stats", params={"weeks": 0}).status_code == 422
