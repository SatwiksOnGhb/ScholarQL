"""Tests for /search and the vector-search filter logic.

The real search needs MongoDB and the embedding model, so endpoint tests swap in fakes.
"""

import pytest
from fastapi.testclient import TestClient

from app.errors import ApiError
from app.main import app
from app.models.search import SearchHit
from app.routers import search as search_router
from app.services.paper_lookup import VenueCount
from app.services.vector_search import mongo_filter


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        (None, None),
        ({}, None),
        ({"year_from": 2021}, {"year": {"$gte": 2021}}),
        ({"year_from": 2019, "year_to": 2021}, {"year": {"$gte": 2019, "$lte": 2021}}),
        ({"venue_id": 42}, {"venue_id": {"$eq": 42}}),
        (
            {"year_from": 2020, "venue_id": 42},
            {"$and": [{"year": {"$gte": 2020}}, {"venue_id": {"$eq": 42}}]},
        ),
    ],
)
def test_mongo_filter(filters, expected):
    assert mongo_filter(filters) == expected


def test_search_passes_filters_and_returns_hits(client, monkeypatch):
    calls = []

    async def fake_search_papers(text, k, filters):
        calls.append((text, k, filters))
        return [SearchHit(paper_id=1, score=0.9, title="A paper", year=2021)]

    monkeypatch.setattr(search_router, "search_papers", fake_search_papers)
    r = client.get("/search", params={"q": " graphs ", "k": 5, "year_from": 2020, "venue_id": 7})
    assert r.status_code == 200
    assert r.json()["results"][0]["title"] == "A paper"
    assert calls == [("graphs", 5, {"year_from": 2020, "venue_id": 7})]


def test_search_unavailable_uses_error_format(client, monkeypatch):
    async def broken(*_):
        raise ApiError(503, "service_unavailable", "Search is unavailable right now")

    monkeypatch.setattr(search_router, "search_papers", broken)
    r = client.get("/search", params={"q": "x"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "service_unavailable"


def test_venues(client, monkeypatch):
    async def fake_top_venues(limit):
        return [VenueCount(venue_id=7, name="NeurIPS", paper_count=12)][:limit]

    monkeypatch.setattr(search_router, "top_venues", fake_top_venues)
    r = client.get("/search/venues")
    assert r.json() == {"venues": [{"venue_id": 7, "name": "NeurIPS", "paper_count": 12}]}
