"""Tests for query logging and feedback. MongoDB calls are replaced with fakes."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.errors import ApiError
from app.main import app
from app.models.ask import Answer
from app.routers import ask as ask_router
from app.services.query_log import build_log_doc

ANSWER = Answer(
    sql="SELECT 1",
    columns=["x"],
    rows=[[1], [2]],
    route="hybrid",
    explanation="e",
    attempts=2,
    latency_ms=5,
)
QID = "0123456789abcdef01234567"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_build_log_doc_success():
    now = datetime(2026, 10, 24, tzinfo=UTC)
    doc = build_log_doc("q?", ANSWER, latency_ms=120, now=now)
    assert doc == {
        "question": "q?",
        "sql": "SELECT 1",
        "route": "hybrid",
        "ok": True,
        "latency_ms": 120,
        "error": None,
        "feedback": None,
        "created_at": now,
        "attempts": 2,
        "row_count": 2,
    }


def test_build_log_doc_failure():
    doc = build_log_doc("q?", None, latency_ms=40, error="Timeout: too slow", route="semantic")
    assert doc["ok"] is False
    assert doc["route"] == "semantic"
    assert doc["sql"] is None
    assert doc["error"] == "Timeout: too slow"
    assert "attempts" not in doc


@pytest.fixture(autouse=True)
def fake_engine(monkeypatch):
    """B's engine needs both databases; these tests are about logging, so fake its answer."""

    async def fake_answer(question):
        return ANSWER.model_copy()

    monkeypatch.setattr(ask_router.engine, "answer", fake_answer)


@pytest.fixture
def logged(monkeypatch):
    """Capture log_query calls instead of writing to MongoDB."""
    calls = []

    async def fake_log_query(question, answer, **kwargs):
        calls.append({"question": question, "answer": answer, **kwargs})
        return QID

    monkeypatch.setattr(ask_router, "log_query", fake_log_query)
    return calls


def test_ask_logs_answer_and_returns_query_id(client, logged):
    r = client.post("/ask", json={"question": "  papers from 2020  "})
    assert r.status_code == 200
    body = r.json()
    assert body["query_id"] == QID
    for field in ("sql", "columns", "rows", "route", "explanation", "attempts", "latency_ms"):
        assert field in body
    assert logged[0]["question"] == "papers from 2020"
    assert logged[0]["answer"].route == body["route"]


def test_ask_still_answers_when_logging_is_down(client, monkeypatch):
    async def no_mongo(*_, **__):
        return None  # log_query swallows MongoDB errors and returns None

    monkeypatch.setattr(ask_router, "log_query", no_mongo)
    r = client.post("/ask", json={"question": "papers from 2020"})
    assert r.status_code == 200
    assert r.json()["query_id"] is None


def test_ask_logs_engine_failure(client, logged, monkeypatch):
    async def broken(question):
        raise TimeoutError("LLM took too long")

    monkeypatch.setattr(ask_router.engine, "answer", broken)
    r = client.post("/ask", json={"question": "papers from 2020"})
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "engine_error"
    assert logged[0]["answer"] is None
    assert logged[0]["error"] == "TimeoutError: LLM took too long"


def test_feedback_stores_verdict(client, monkeypatch):
    calls = []

    async def fake_record(query_id, correct, comment):
        calls.append((query_id, correct, comment))

    monkeypatch.setattr(ask_router, "record_feedback", fake_record)
    r = client.post("/feedback", json={"query_id": QID, "correct": False, "comment": "wrong"})
    assert r.json() == {"ok": True}
    assert calls == [(QID, False, "wrong")]


def test_feedback_unknown_id_is_404(client, monkeypatch):
    async def missing(query_id, *_):
        raise ApiError(404, "not_found", f"No logged query with id {query_id}")

    monkeypatch.setattr(ask_router, "record_feedback", missing)
    r = client.post("/feedback", json={"query_id": QID, "correct": True})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_feedback_rejects_malformed_id(client):
    r = client.post("/feedback", json={"query_id": "abc", "correct": True})
    assert r.status_code == 422


def test_ask_unanswerable_question_is_422_and_logged(client, logged, monkeypatch):
    async def unsupported(question):
        raise ask_router.engine.UnsupportedQuestion("Add a research concept.")

    monkeypatch.setattr(ask_router.engine, "answer", unsupported)
    r = client.post("/ask", json={"question": "since 2021"})
    assert r.status_code == 422
    assert r.json()["error"] == {
        "code": "unanswerable",
        "message": "Add a research concept.",
        "details": None,
    }
    assert logged[0]["error"] == "UnsupportedQuestion: Add a research concept."
