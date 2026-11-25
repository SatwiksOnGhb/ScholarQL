"""A's endpoints (/papers, /papers/{id}, /citations, /trends) on the pilot PostgreSQL."""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.routers.papers import growth
from tests.conftest import TEST_DATABASE_URL, needs_postgres

pytestmark = needs_postgres

QLORA = "W7133233472"  # in the pilot, arXiv 2305.14314


@pytest.fixture(scope="module")
def client():
    original = settings.database_url
    settings.database_url = TEST_DATABASE_URL
    try:
        with TestClient(app) as c:
            yield c
    finally:
        settings.database_url = original


def test_list_papers(client):
    r = client.get("/papers", params={"limit": 5, "year_from": 2020})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] > 5 and len(body["items"]) == 5
    assert all(p["year"] >= 2020 for p in body["items"])
    counts = [p["citation_count"] for p in body["items"]]
    assert counts == sorted(counts, reverse=True)


def test_get_paper(client):
    r = client.get(f"/papers/{QLORA}")
    assert r.status_code == 200
    p = r.json()
    assert p["title"].startswith("QLoRA") and p["arxiv_id"] == "2305.14314"
    assert p["authors"] and p["authors"][0]["author_order"] == 1
    assert any(t["topic_id"] == "cs.LG" for t in p["topics"])


def test_missing_paper_is_404(client):
    r = client.get("/papers/W0")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_citation_graph(client):
    r = client.get(f"/papers/{QLORA}/citations", params={"depth": 2})
    assert r.status_code == 200
    g = r.json()
    ids = {n["paper_id"] for n in g["nodes"]}
    assert QLORA in ids
    assert all(e["citing_id"] in ids and e["cited_id"] in ids for e in g["edges"])
    assert max(n["depth"] for n in g["nodes"]) <= 2


def test_trends(client):
    r = client.get("/trends", params={"limit": 3})
    assert r.status_code == 200
    t = r.json()
    assert len(t["topics"]) == 3
    assert all(len(topic["counts"]) == 2024 - 2018 + 1 for topic in t["topics"])


def test_growth():
    assert growth([10, 20]) == 1.0
    assert growth([0, 5]) == 5.0
