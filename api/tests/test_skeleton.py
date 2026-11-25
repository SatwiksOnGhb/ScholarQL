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


def test_unknown_route_uses_error_format(client):
    r = client.get("/no-such-route")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_validation_uses_error_format(client):
    r = client.get("/search", params={"q": "x", "k": 0})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_openapi_documents_error_shape(client):
    spec = client.get("/openapi.json").json()
    assert "ErrorResponse" in spec["components"]["schemas"]
