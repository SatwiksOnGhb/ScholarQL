"""Insert fake query_logs so the analytics page has data before B's engine is live.

The fake history tells a plausible story: usage grows week over week, accuracy improves
(as self-correction would make it), and failures have realistic causes. Every document is
tagged `seed: true`, so --clear removes only fake logs and never real ones.

TODO(B): once real /ask traffic exists, stop seeding (or run with --clear to remove it).

Usage (from jobs/):
    uv run python -m seed.query_logs              # 2000 logs over the last 8 weeks
    uv run python -m seed.query_logs --n 1500 --weeks 12
    uv run python -m seed.query_logs --clear      # remove seeded logs only
"""

import argparse
import math
import random
from datetime import UTC, datetime, timedelta

from common import mongo_db

# (question, route) with a popularity weight, so "top questions" has a real head and tail
QUESTIONS = [
    ("Top 10 venues by average citations since 2020", "sql", 14),
    ("Papers by Geoffrey Hinton in 2021", "sql", 11),
    ("Papers about diffusion models", "semantic", 10),
    ("How many papers were published at NeurIPS each year?", "sql", 9),
    ("Authors from Google publishing at ICLR", "sql", 8),
    ("Recent work on graph neural networks for molecules", "hybrid", 8),
    ("Papers similar to Attention Is All You Need", "semantic", 7),
    ("Citation chain 3 levels deep from BERT", "sql", 7),
    ("Most cited reinforcement learning papers after 2019", "hybrid", 6),
    ("Which institutions publish the most on fairness?", "hybrid", 5),
    ("Papers that cite SimCLR but not MoCo", "sql", 5),
    ("Explainable AI methods for medical imaging", "semantic", 5),
    ("Authors who published in both vision and RL venues after 2020", "sql", 4),
    ("Fastest growing topics in 2023", "sql", 4),
    ("Self-supervised learning papers from Meta in 2022", "hybrid", 4),
    ("Survey papers on federated learning", "semantic", 3),
    ("Average number of authors per paper by year", "sql", 3),
    ("Papers on efficient fine-tuning of large language models", "semantic", 3),
    ("Co-authors of Yoshua Bengio", "sql", 2),
    ("Prompt tuning papers cited by more than 100 papers", "hybrid", 2),
]
SQL_EXAMPLES = {
    "sql": "SELECT v.name, avg(p.citation_count) FROM paper p JOIN venue v USING (venue_id) "
    "WHERE p.year >= 2020 GROUP BY v.name ORDER BY 2 DESC LIMIT 10",
    "hybrid": "SELECT p.title, p.citation_count FROM paper p WHERE p.paper_id = ANY(%(ids)s) "
    "ORDER BY p.citation_count DESC LIMIT 20",
}
# Per route: accuracy at the start -> end of the window, failure rate start -> end,
# median latency in ms, latency spread (lognormal sigma)
PROFILE = {
    "sql": {"acc": (0.60, 0.84), "fail": (0.12, 0.04), "median": 1800, "sigma": 0.45},
    "semantic": {"acc": (0.74, 0.86), "fail": (0.03, 0.02), "median": 320, "sigma": 0.35},
    "hybrid": {"acc": (0.48, 0.74), "fail": (0.15, 0.07), "median": 2600, "sigma": 0.5},
}
FAILURES = {  # error -> weight; the part before ":" is what analytics groups by
    "sql": [
        ("SQLExecutionError: column p.citations does not exist", 5),
        ("TimeoutError: statement timeout after 5s", 3),
        ("UnsafeSQLError: only a single SELECT is allowed", 2),
        ("RateLimitError: Gemini quota exceeded", 2),
    ],
    "semantic": [("RateLimitError: Gemini quota exceeded", 1), ("TimeoutError: vector search", 1)],
    "hybrid": [
        ("SQLExecutionError: operator does not exist: bigint = text", 3),
        ("TimeoutError: statement timeout after 5s", 3),
        ("RateLimitError: Gemini quota exceeded", 2),
    ],
}
FEEDBACK_RATE = 0.6  # share of answers that get a thumbs up/down


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def fake_log(rng: random.Random, now: datetime, weeks: int) -> dict:
    # Usage grows over time: sample the age so recent days are more likely
    t = rng.random() ** 0.7  # 0 = start of window, 1 = now (skewed towards recent)
    created = now - timedelta(days=weeks * 7 * (1 - t), seconds=rng.randint(0, 3600))
    question, route, _ = rng.choices(QUESTIONS, weights=[q[2] for q in QUESTIONS])[0]
    p = PROFILE[route]

    failed = rng.random() < lerp(*p["fail"], t)
    error = None
    if failed:
        errors = FAILURES[route]
        error = rng.choices([e for e, _ in errors], weights=[w for _, w in errors])[0]
    latency = rng.lognormvariate(math.log(p["median"]), p["sigma"])
    if error and error.startswith("TimeoutError"):
        latency = rng.uniform(5000, 5600)

    attempts = 1 if route == "semantic" else rng.choices([1, 2, 3], weights=[75, 18, 7])[0]
    doc = {
        "question": question,
        "sql": None if route == "semantic" or failed else SQL_EXAMPLES[route],
        "route": route,
        "ok": not failed,
        "latency_ms": round(latency),
        "error": error,
        "feedback": None,
        "created_at": created,
        "attempts": attempts,
        "seed": True,
    }
    if not failed:
        doc["row_count"] = rng.randint(1, 50)
        if rng.random() < FEEDBACK_RATE:
            doc["feedback"] = {
                "correct": rng.random() < lerp(*p["acc"], t),
                "comment": None,
                "created_at": created + timedelta(seconds=rng.randint(5, 120)),
            }
    return doc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--n", type=int, default=2000, help="number of logs (default 2000)")
    parser.add_argument("--weeks", type=int, default=8, help="spread over this many weeks")
    parser.add_argument("--seed", type=int, default=42, help="random seed (repeatable data)")
    parser.add_argument("--clear", action="store_true", help="only delete seeded logs")
    args = parser.parse_args()

    logs = mongo_db().query_logs
    removed = logs.delete_many({"seed": True}).deleted_count
    print(f"Removed {removed} previously seeded logs")
    if args.clear:
        return

    rng = random.Random(args.seed)
    now = datetime.now(UTC)
    docs = [fake_log(rng, now, args.weeks) for _ in range(args.n)]
    logs.insert_many(docs)
    failed = sum(not d["ok"] for d in docs)
    rated = sum(d["feedback"] is not None for d in docs)
    print(f"Inserted {len(docs)} logs over {args.weeks} weeks ({failed} failed, {rated} rated)")


if __name__ == "__main__":
    main()
