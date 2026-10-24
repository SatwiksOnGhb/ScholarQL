"""Tests for the reviewer finder. The real search needs MongoDB, so endpoints use fakes."""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.reviewers import AuthorOption, ExcludedAuthor, ReviewerResponse
from app.routers import reviewers as reviewers_router
from app.services.reviewers import Candidate, rank_papers, select_candidates


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _candidate(author_id: int, score: float) -> Candidate:
    return Candidate(author_id, f"A{author_id}", None, [], score)


def test_select_candidates_drops_blocked_and_keeps_order():
    cands = [_candidate(i, 1 - i / 10) for i in range(1, 7)]
    chosen = select_candidates(cands, blocked={2, 4}, k=3)
    assert [c.author_id for c in chosen] == [1, 3, 5]


def test_select_candidates_with_fewer_than_k():
    assert len(select_candidates([_candidate(1, 0.9)], blocked=set(), k=5)) == 1


def test_rank_papers_uses_cosine_on_atlas_scale():
    query = np.array([1.0, 0.0])
    vectors = {1: np.array([1.0, 0.0]), 2: np.array([0.0, 1.0]), 3: np.array([-1.0, 0.0])}
    ranked = rank_papers(query, vectors, [3, 2, 1, 99], n=2)  # 99 has no vector: skipped
    assert ranked == [(1, 1.0), (2, 0.5)]


def test_reviewers_endpoint_passes_request(client, monkeypatch):
    calls = []

    async def fake_find(abstract, author_ids, k):
        calls.append((abstract, author_ids, k))
        return ReviewerResponse(
            reviewers=[],
            excluded_authors=[ExcludedAuthor(author_id=7, name="X", reason="submitting_author")],
            excluded_institutions=[],
        )

    monkeypatch.setattr(reviewers_router, "find_reviewers", fake_find)
    body = {"abstract": "  " + "a" * 30 + "  ", "author_ids": [7], "k": 3}
    r = client.post("/reviewers", json=body)
    assert r.status_code == 200
    assert r.json()["excluded_authors"][0]["reason"] == "submitting_author"
    assert calls == [("a" * 30, [7], 3)]


def test_reviewers_rejects_short_abstract(client):
    r = client.post("/reviewers", json={"abstract": "too short"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_author_picker(client, monkeypatch):
    async def fake_search(q, limit):
        return [AuthorOption(author_id=1, name="Ting Chen", paper_count=2)]

    monkeypatch.setattr(reviewers_router, "search_authors", fake_search)
    r = client.get("/reviewers/authors", params={"q": "chen"})
    assert r.json()["authors"][0]["name"] == "Ting Chen"
    assert client.get("/reviewers/authors", params={"q": "c"}).status_code == 422  # min 2 chars
