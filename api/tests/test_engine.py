"""B's engine behind contract 3 (scholarql.answer): routing, SQL answers, and the semantic /
hybrid ranking over C's MongoDB vectors (MongoDB faked with mongomock)."""

import mongomock
import numpy as np
import pytest
from scholarql import answer as eng

from tests.conftest import TEST_READER_URL, needs_postgres

DIM = 384


def unit(seed: int) -> list[float]:
    v = np.random.default_rng(seed).normal(size=DIM)
    return (v / np.linalg.norm(v)).astype(np.float32).tolist()


def test_jsonable_converts_dates_and_decimals():
    from datetime import date
    from decimal import Decimal

    assert eng._jsonable([date(2024, 1, 2), Decimal("1.5"), ("a", 1)]) == [
        "2024-01-02",
        1.5,
        ["a", 1],
    ]


def test_generator_prefers_configured_llm(monkeypatch):
    class Fake:
        providers = {"groq": object()}

    monkeypatch.delenv("SCHOLARQL_GENERATOR", raising=False)
    assert eng._generator(Fake()) == "groq"
    Fake.providers = {}
    assert eng._generator(Fake()) == "local"
    monkeypatch.setenv("SCHOLARQL_GENERATOR", "local")
    Fake.providers = {"gemini": object()}
    assert eng._generator(Fake()) == "local"


@pytest.fixture
def engine(monkeypatch):
    """The real engine on the pilot PostgreSQL, with an in-memory MongoDB."""
    monkeypatch.setenv("SCHOLARQL_GENERATOR", "local")
    monkeypatch.setattr(eng, "MongoClient", mongomock.MongoClient)
    vectors: dict[str, list[float]] = {}

    def embed(text: str) -> list[float]:
        return vectors.get(text, unit(0))

    eng.configure(
        database_url=TEST_READER_URL, mongodb_uri="mongodb://x", mongodb_db="test", embed=embed
    )
    yield eng._engine, vectors
    eng.close()


@needs_postgres
def test_sql_question(engine):
    result = eng.answer("Find arXiv paper 2305.14314")
    assert result["route"] == "sql"
    assert "arxiv_id = '2305.14314'" in result["sql"]
    assert result["rows"][0][1].startswith("QLoRA")
    assert result["attempts"] == 1
    assert set(result) == {
        "sql",
        "columns",
        "rows",
        "route",
        "explanation",
        "attempts",
        "latency_ms",
    }


@needs_postgres
def test_unsupported_question_raises(engine):
    with pytest.raises(eng.UnsupportedQuestion):
        eng.answer("Papers about transformers since 2021 or before 2019")


@needs_postgres
def test_hybrid_ranks_filtered_papers_with_mongo_vectors(engine):
    eng_obj, vectors = engine
    db = eng_obj.documents.mongo
    rows = eng_obj.db.run(
        "SELECT paper_id, publication_year FROM paper ORDER BY paper_id", cap=1000
    ).rows
    for i, (pid, year) in enumerate(rows):
        db.paper_content.insert_one(
            {"_id": pid, "abstract": f"abstract {pid}", "year": year, "embedding": unit(i + 1)}
        )
    recent = [(i, pid) for i, (pid, year) in enumerate(rows) if year >= 2023]
    target_index, target = recent[0]
    vectors["diffusion models"] = unit(target_index + 1)  # the query equals its vector

    result = eng.answer("Find papers about diffusion models published since 2023")
    assert result["route"] == "hybrid"
    assert "2023" in result["sql"]
    assert result["columns"] == ["paper_id", "title", "year", "score"]
    assert result["rows"][0][0] == target
    assert result["rows"][0][3] == pytest.approx(1.0, abs=1e-4)
    assert all(row[2] >= 2023 for row in result["rows"])


@needs_postgres
def test_semantic_falls_back_to_tfidf_without_vectors(engine):
    eng_obj, _ = engine
    db = eng_obj.documents.mongo
    rows = eng_obj.db.run("SELECT paper_id FROM paper ORDER BY paper_id LIMIT 3", cap=3).rows
    db.paper_content.insert_many(
        [
            {"_id": rows[0][0], "abstract": "graph neural networks for molecules", "year": 2020},
            {"_id": rows[1][0], "abstract": "reinforcement learning for robots", "year": 2020},
            {"_id": rows[2][0], "abstract": "image segmentation", "year": 2021},
        ]
    )
    result = eng.answer("Explain graph neural networks for molecules")
    assert result["route"] == "semantic"
    assert result["sql"] is None
    assert result["rows"][0][0] == rows[0][0]
    assert "TF-IDF" in result["explanation"]
