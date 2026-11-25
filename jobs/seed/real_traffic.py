"""Ask the live API a set of real questions, so the analytics page shows real usage.

Unlike seed/query_logs.py (fake logs for a demo), every question here goes through the real
engine: real routes, real latencies, real failures. Answers are not rated automatically;
rate some on the Ask page (thumbs up/down) so the accuracy chart has real ratings.

    uv run python -m seed.real_traffic                      # against the deployed API
    uv run python -m seed.real_traffic --api http://localhost:8000
"""

import argparse
import time

import httpx

QUESTIONS = [
    # SQL: lookups, joins, aggregations, recursion, set operations
    "Top 5 venues by average citations since 2021",
    "Find arXiv paper 2106.09685",
    "Find arXiv paper 2303.08774",
    "Find arXiv paper 2010.11929",
    'Show the citation chain from "GPT-4 Technical Report" up to depth 2',
    'Show the citation chain from "LoRA: Low-Rank Adaptation of Large Language Models" '
    "up to depth 1",
    'Papers that cite "LoRA: Low-Rank Adaptation of Large Language Models" '
    'but not "GPT-4 Technical Report"',
    "Top 10 venues by number of papers since 2022",
    "How many papers were published in 2023?",
    "Which authors have written the most papers?",
    "Which institutions have the most papers?",
    "Average citations per paper by publication year",
    "Top 10 most cited papers published in 2022",
    # Semantic
    "Explain how diffusion models generate images",
    "diffusion models image generation",
    "graph neural networks for molecules",
    "contrastive representation learning",
    "teaching computers to play games by trial and error",
    "making neural networks smaller and faster",
    "federated learning privacy",
    # Hybrid: meaning plus exact filters
    "Find papers about adapting language models on a small GPU published since 2023",
    "reinforcement learning from human feedback since 2022",
    "papers about LoRA fine-tuning since 2023",
    "papers about graph neural networks since 2021",
    "papers about adversarial robustness since 2020",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--api", default="https://scholarql-api.onrender.com")
    parser.add_argument("--rounds", type=int, default=1, help="ask the whole set this many times")
    args = parser.parse_args()

    with httpx.Client(base_url=args.api, timeout=120) as client:
        print("Waking up the API...", flush=True)
        client.get("/health")
        ok = failed = 0
        for _ in range(args.rounds):
            for q in QUESTIONS:
                started = time.monotonic()
                res = client.post("/ask", json={"question": q})
                secs = time.monotonic() - started
                if res.status_code == 200:
                    body = res.json()
                    ok += 1
                    print(f"ok    {body['route']:8} {len(body['rows']):4} rows {secs:5.1f}s  {q}")
                else:
                    failed += 1
                    print(f"FAIL  HTTP {res.status_code}           {secs:5.1f}s  {q}")
                time.sleep(7)  # /ask allows 10 questions a minute per IP
    print(f"\nDone: {ok} answered, {failed} failed. Every question is now in query_logs.")


if __name__ == "__main__":
    main()
