"""Evaluate hard-filter placement and retriever choice on the frozen arXiv pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from time import perf_counter

import numpy as np
from scholarql.config import DATA, PILOT, ROOT
from scholarql.db import Database
from scholarql.intents import extract_filters
from scholarql.retrieval import MODEL_REVISION, MiniLM, TextIndex, load_documents, model_directory

from .index_study import write_csv

QRELS = DATA / "retrieval_qrels.jsonl"
METHODS = {
    "bm25_prefilter": ("bm25", "prefilter"),
    "tfidf_prefilter": ("tfidf", "prefilter"),
    "minilm_vector_only": ("minilm", "none"),
    "minilm_postfilter": ("minilm", "postfilter"),
    "minilm_prefilter": ("minilm", "prefilter"),
}


def measures(ranked, grades, eligible, k):
    hits = [grades.get(paper_id, 0) for paper_id in ranked]
    discounted = lambda values: sum(
        (2**grade - 1) / math.log2(i + 2) for i, grade in enumerate(values)
    )
    ideal = discounted(sorted(grades.values(), reverse=True)[:k])
    return {
        "recall": sum(grade > 0 for grade in hits) / len(grades),
        "ndcg": discounted(hits) / ideal,
        "mrr": next((1 / (i + 1) for i, grade in enumerate(hits) if grade > 0), 0.0),
        "eligible_returned": len(set(ranked) & eligible),
        "returned": len(ranked),
        "violations": len(set(ranked) - eligible),
        "nonempty": int(bool(ranked)),
    }


def summarize(rows):
    count = len(rows)
    total_returned = sum(row["returned"] for row in rows)
    return {
        "n": count,
        **{
            stat: round(sum(row[stat] for row in rows) / count, 5)
            for stat in ("recall", "ndcg", "mrr")
        },
        "eligibility": round(sum(row["eligible_returned"] for row in rows) / total_returned, 5)
        if total_returned
        else 0,
        "queries_with_violations": sum(bool(row["violations"]) for row in rows),
        "nonempty_rate": round(sum(row["nonempty"] for row in rows) / count, 5),
        "mean_results": round(total_returned / count, 3),
        "p95_ms": round(float(np.quantile([row["latency_ms"] for row in rows], 0.95)), 4),
    }


def run(out: Path, k: int, dense: bool):
    out.mkdir(parents=True, exist_ok=True)
    db = Database()
    encoder = MiniLM(model_directory()) if dense else None
    index = TextIndex(load_documents(PILOT), encoder)
    if dense:
        index.embeddings()
        encoder.encode(["warm the encoder"])
    documents = set(index.positions)
    studies = [
        json.loads(line) for line in QRELS.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    measurements = []
    methods = {
        name: (ranker, placement)
        for name, (ranker, placement) in METHODS.items()
        if dense or ranker != "minilm"
    }
    for item in studies:
        filters = extract_filters(item["question"])
        if bool(filters.conditions) != (item["group"] == "hybrid"):
            raise ValueError(f"Filter grouping mismatch: {item['id']}")
        all_eligible = {row[0] for row in db.run(filters.sql, cap=100_000).rows} & documents
        if not set(item["judgments"]).issubset(all_eligible):
            raise ValueError(
                f"Gold judgment violates parsed metadata: {item['id']}: {set(item['judgments']) - all_eligible}"
            )
        for name, (ranker, placement) in methods.items():
            # Warm-query latency excludes fixture loading and embedding build.
            times = []
            for _ in range(3):
                started = perf_counter()
                allowed = (
                    {row[0] for row in db.run(filters.sql, cap=100_000).rows} & documents
                    if placement != "none"
                    else None
                )
                ranked = index.rank(
                    filters.concept,
                    eligible=allowed if placement == "prefilter" else None,
                    k=k,
                    mode=ranker,
                )
                ids = [
                    row["paper_id"]
                    for row in ranked
                    if placement != "postfilter" or row["paper_id"] in allowed
                ]
                times.append(1000 * (perf_counter() - started))
            measurements.append(
                {
                    "id": item["id"],
                    "group": item["group"],
                    "method": name,
                    "question": item["question"],
                    "eligible_candidates": len(all_eligible),
                    **measures(ids, item["judgments"], all_eligible, k),
                    "latency_ms": round(float(np.median(times)), 5),
                    "paper_ids": "|".join(ids),
                }
            )
    summaries = {
        group: {
            method: summarize(
                [r for r in measurements if r["group"] == group and r["method"] == method]
            )
            for method in methods
        }
        for group in ("semantic", "hybrid")
    }
    paired = None
    if dense:
        series = {}
        for method in ("minilm_prefilter", "minilm_postfilter"):
            series[method] = [
                r["recall"]
                for r in measurements
                if r["group"] == "hybrid" and r["method"] == method
            ]
        values = np.asarray(series["minilm_prefilter"]) - np.asarray(series["minilm_postfilter"])
        rng = np.random.default_rng(4801)
        samples = rng.choice(values, size=(10000, len(values)), replace=True).mean(axis=1)
        paired = {
            "comparison": "MiniLM prefilter minus MiniLM postfilter, absolute Recall@5 on the 16 hybrid questions",
            "mean_delta": round(float(values.mean()), 5),
            "bootstrap_95": [round(float(x), 5) for x in np.quantile(samples, [0.025, 0.975])],
            "n_resamples": 10000,
            "seed": 4801,
        }
        if k != 5:
            paired["comparison"] = paired["comparison"].replace("Recall@5", f"Recall@{k}")
    write_csv(out / "retrieval_cases.csv", measurements)
    result = {
        "metadata": {
            "questions": len(studies),
            "documents": len(documents),
            "k": k,
            "miniLM_revision": MODEL_REVISION if dense else None,
            "onnx_sha256": encoder.fingerprint if dense else None,
            "pilot_sha256": hashlib.sha256(PILOT.read_bytes()).hexdigest(),
            "qrels_sha256": hashlib.sha256(QRELS.read_bytes()).hexdigest(),
        },
        "summaries": summaries,
        "paired_hybrid_recall": paired,
    }
    (out / "retrieval_results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(summaries["hybrid"], indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--dense", action="store_true")
    args = parser.parse_args()
    if args.k < 1:
        parser.error("--k must be positive")
    run(args.out, args.k, args.dense)


if __name__ == "__main__":
    main()
