from __future__ import annotations

import os
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient
from scholarql.api import app
from scholarql.db import Database
from scholarql.engine import execute_generated
from scholarql.safety import QueryError, validate_sql


class InvalidThenValidProvider:
    def generate(self, question, strategy, dialect, *, feedback=None, **kwargs):
        if feedback:
            return "SELECT count(*) AS paper_count FROM paper"
        return "SELECT wrong_column FROM paper"


class ProjectTest(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ, {"SCHOLARQL_LOG_QUERIES": "0"})
        cls.environment.start()
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        cls.environment.stop()

    def test_pilot_status_and_abstract(self):
        status = self.client.get("/api/status").json()
        self.assertEqual(status["totals"]["papers"], 353)
        search = self.client.get("/api/papers", params={"q": "2305.14314"}).json()
        self.assertEqual(search["total"], 1)
        paper_id = search["items"][0]["paper_id"]
        paper = self.client.get(f"/api/papers/{paper_id}").json()
        self.assertEqual(paper["arxiv_id"], "2305.14314")
        self.assertGreater(len(paper["abstract"]), 100)
        self.assertIn("cs.LG", paper["topics"])

    def test_hybrid_candidates_equal_sql_scope(self):
        question = 'Find papers about quantized language models since 2023 tagged "cs.LG"'
        result = self.client.post("/api/query", json={"question": question, "k": 5}).json()
        self.assertEqual(result["route"], "hybrid")
        self.assertEqual(result["status"], "answered")
        self.assertTrue(result["papers"])
        self.assertTrue(
            all(
                p["publication_year"] >= 2023 and "cs.LG" in p["categories"]
                for p in result["papers"]
            )
        )
        self.assertTrue("SELECT p.paper_id" in result["sql"])

    def test_relational_aggregation_and_recursion(self):
        for question in [
            "Top 5 venues by average citations since 2021",
            'Show the citation chain from "Mistral 7B" up to depth 2',
        ]:
            result = self.client.post("/api/query", json={"question": question}).json()
            self.assertEqual(result["route"], "sql")
            self.assertEqual(result["status"], "answered")
            self.assertGreater(len(result["rows"]), 0)

    def test_citation_directions_and_evaluation(self):
        for direction in ("incoming", "outgoing"):
            result = self.client.get(
                "/api/citations/W4387561528", params={"direction": direction, "depth": 2}
            )
            self.assertEqual(result.status_code, 200)
            self.assertTrue(result.json()["edges"])
        self.assertEqual(self.client.get("/api/artifacts/evaluation").status_code, 200)

    def test_unsupported_question_abstains(self):
        result = self.client.post(
            "/api/query", json={"question": "How many papers do you know about?"}
        ).json()
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(result["rows"], [])

    def test_validation_and_retry_path(self):
        self.assertEqual(validate_sql("SELECT title FROM paper"), "SELECT title FROM paper")
        for statement in (
            "SELECT paper_id FROM other_collection",
            "UPDATE paper SET cited_by_count = 0",
            "SELECT title FROM paper; SELECT title FROM paper",
        ):
            with self.assertRaises(QueryError):
                validate_sql(statement)
        trial = execute_generated(
            Database.from_environment(),
            "Count papers",
            InvalidThenValidProvider(),
            "few_shot_correction",
        )
        self.assertEqual([a["status"] for a in trial.attempts], ["rejected", "executed"])
        self.assertEqual(trial.result.rows, [(353,)])
        self.assertEqual(trial.planner_checked, Database.from_environment().postgres)
