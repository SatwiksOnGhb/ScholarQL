"""Smoke tests for the walking skeleton: every route answers in its agreed shape.

They don't need the databases; /health just reports them as down when they're missing.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # `with` runs the startup/shutdown lifespan
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert set(r.json()) == {"status", "postgres", "mongodb"}


@pytest.mark.parametrize(
    "path",
    ["/papers/1001", "/papers/1001/citations?depth=2", "/trends", "/search?q=bert", "/admin/stats"],
)
def test_get_routes(client, path):
    assert client.get(path).status_code == 200


def test_ask_returns_answer_shape(client):
    r = client.post("/ask", json={"question": "papers from 2020"})
    assert r.status_code == 200
    body = r.json()
    for field in ("sql", "columns", "rows", "route", "explanation", "attempts", "latency_ms"):
        assert field in body


def test_reviewers_excludes_coauthors(client):
    r = client.post("/reviewers", json={"abstract": "x" * 30, "author_ids": [5004]})
    assert r.status_code == 200
    body = r.json()
    assert body["excluded_author_ids"] == [5004, 5005]  # 5005 co-authored with 5004
    assert all(rv["author_id"] not in (5004, 5005) for rv in body["reviewers"])


def test_feedback(client):
    r = client.post("/feedback", json={"query_id": "abc", "correct": True})
    assert r.json() == {"ok": True}


def test_not_found_uses_error_format(client):
    r = client.get("/papers/999")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_validation_uses_error_format(client):
    r = client.get("/search", params={"q": "x", "k": 0})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_openapi_documents_error_shape(client):
    spec = client.get("/openapi.json").json()
    assert "ErrorResponse" in spec["components"]["schemas"]
