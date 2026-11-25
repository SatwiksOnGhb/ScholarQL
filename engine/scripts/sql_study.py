"""Run four-tier execution evaluation on held-fixed data and a counterfactual snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import Counter
from decimal import Decimal
from pathlib import Path
from time import perf_counter

import numpy as np
from scholarql.config import DATA, PILOT, ROOT
from scholarql.db import DB_ERRORS, Database, QueryRows, install_pilot, read_pilot
from scholarql.engine import execute_generated
from scholarql.intents import compile_question
from scholarql.providers import STRATEGIES, Provider
from scholarql.safety import QueryError, validate_sql

from .index_study import write_csv

QUESTION_FILE = DATA / "sql_benchmark.jsonl"


def make_counterfactual(path: Path):
    fixture = read_pilot()
    data = fixture["entities"]
    paper_ids = [paper[0] for paper in data["paper"]]
    for index, paper in enumerate(data["paper"]):
        if index % 7 == 0:
            paper[2] = 2018 + (paper[2] - 2018 + 2) % 7
            paper[3] = str(paper[2]) + "-03-01"
    changed = [tuple(row) for idx, row in enumerate(data["citation"]) if idx % 5 != 0]
    for index in range(9, len(paper_ids), 11):
        if all((src, dst) != (paper_ids[index], paper_ids[index - 6]) for src, dst, _ in changed):
            changed.append((paper_ids[index], paper_ids[index - 6], "other"))
    data["citation"] = sorted(changed)
    path.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")


def canonical(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (float, Decimal)):
        return round(float(value), 6)
    if isinstance(value, list):
        return tuple(map(canonical, value))
    return value


def equal(a: QueryRows, b: QueryRows, ordered: bool):
    if a.truncated or b.truncated or len(a.columns) != len(b.columns):
        return False
    aa, bb = ([tuple(map(canonical, row)) for row in data.rows] for data in (a, b))
    return aa == bb if ordered else Counter(aa) == Counter(bb)


def assess(db, alternate, cases, provider=None, strategy="local"):
    result = []
    for case in cases:
        gold = validate_sql(case["gold_sql"])
        reference, alt_reference = [d.run(gold, cap=10000) for d in (db, alternate)]
        if reference.truncated or alt_reference.truncated:
            raise ValueError("Unexpected gold truncation: " + case["id"])
        started = perf_counter()
        predicted, sql, tries, error = None, "", [], ""
        if provider:
            attempt = execute_generated(
                db, case["question"], provider, strategy, cap=10000, projection=reference.columns
            )
            predicted, sql, tries, error = (
                attempt.result,
                attempt.sql,
                attempt.attempts,
                attempt.error,
            )
        else:
            sql = compile_question(case["question"]) or ""
            if sql:
                try:
                    predicted = db.run(validate_sql(sql), cap=10000)
                except (QueryError, *DB_ERRORS) as exc:
                    error = Database.explain_error(exc)
            else:
                error = "Local wording unsupported."
        elapsed = round(1000 * (perf_counter() - started), 4)
        main_match = predicted is not None and equal(predicted, reference, case["ordered"])
        alt_match = False
        if predicted is not None:
            try:
                alt = alternate.run(validate_sql(sql), cap=10000)
                alt_match = equal(alt, alt_reference, case["ordered"])
            except (QueryError, *DB_ERRORS):
                pass
        result.append(
            {
                "id": case["id"],
                "tier": case["tier"],
                "form": case["form"],
                "wording": case["wording"],
                "strategy": strategy,
                "question": case["question"],
                "executed": int(predicted is not None),
                "pilot_match": int(main_match),
                "counterfactual_match": int(alt_match),
                "joint_match": int(main_match and alt_match),
                "gold_rows": len(reference.rows),
                "counterfactual_gold_rows": len(alt_reference.rows),
                "counterfactual_changed_answer": int(
                    not equal(reference, alt_reference, case["ordered"])
                ),
                "latency_ms": elapsed,
                "repair_attempted": int(len(tries) > 1),
                "repair_matched": int(len(tries) > 1 and main_match and alt_match),
                "error": error,
                "predicted_sql": sql,
            }
        )
    return result


def summarize(queries):
    total = len(queries)
    return {
        "n": total,
        "executed": sum(row["executed"] for row in queries),
        "pilot_correct": sum(row["pilot_match"] for row in queries),
        "counterfactual_correct": sum(row["counterfactual_match"] for row in queries),
        "joint_correct": sum(row["joint_match"] for row in queries),
        "empty_gold": sum(row["gold_rows"] == 0 for row in queries),
        "changed_gold": sum(row["counterfactual_changed_answer"] for row in queries),
        "p95_ms": round(float(np.quantile([row["latency_ms"] for row in queries], 0.95)), 4),
        "repair_attempted": sum(row["repair_attempted"] for row in queries),
        "repair_matched": sum(row["repair_matched"] for row in queries),
    }


def run(out, dsn="", alt_dsn="", vendors=()):
    out.mkdir(exist_ok=True, parents=True)
    cases = [
        json.loads(line)
        for line in QUESTION_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if Counter(case["tier"] for case in cases) != {
        "lookup": 25,
        "joins": 25,
        "aggregation": 25,
        "nested": 25,
    }:
        raise ValueError("Expected 25 questions in each of four tiers.")
    providers = Provider.configured()
    if not all(vendor in providers for vendor in vendors):
        raise ValueError("Set explicit key and model for each selected provider.")
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        fixture = base / "counterfactual.json"
        make_counterfactual(fixture)
        db = Database(dsn, None if dsn else install_pilot(PILOT, base))
        alt = Database(alt_dsn, None if alt_dsn else install_pilot(fixture, base))
        rows = assess(db, alt, cases)
        studies = {"local": rows}
        for vendor in vendors:
            for strategy in STRATEGIES:
                print(f"Running {vendor} {strategy}", flush=True)
                evaluated = assess(db, alt, cases, providers[vendor], strategy)
                rows = rows + evaluated
                studies[f"{vendor}-{strategy}"] = evaluated
        summary = {}
        for name, evaluated in studies.items():
            summary[name] = {
                "overall": summarize(evaluated),
                "tiers": {
                    tier: summarize([row for row in evaluated if row["tier"] == tier])
                    for tier in ("lookup", "joins", "aggregation", "nested")
                },
                "wording": {
                    wording: summarize([row for row in evaluated if row["wording"] == wording])
                    for wording in ("canonical", "paraphrase")
                },
            }
    write_csv(out / "sql_cases.csv", rows)
    data = {
        "primary_engine": db.engine,
        "counterfactual_engine": alt.engine,
        "studies": summary,
        "providers": {vendor: providers[vendor].model for vendor in vendors},
        "benchmark_sha256": hashlib.sha256(QUESTION_FILE.read_bytes()).hexdigest(),
        "pilot_sha256": hashlib.sha256(PILOT.read_bytes()).hexdigest(),
    }
    (out / "sql_results.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(json.dumps({name: result["overall"] for name, result in summary.items()}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.getenv("SCHOLARQL_SQL_BENCH_DSN", ""))
    parser.add_argument(
        "--counterfactual-dsn", default=os.getenv("SCHOLARQL_COUNTERFACTUAL_DSN", "")
    )
    parser.add_argument("--export-counterfactual", type=Path)
    parser.add_argument("--provider", action="append", choices=["gemini", "groq"], default=[])
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    if args.export_counterfactual:
        make_counterfactual(args.export_counterfactual)
        return
    if bool(args.dsn) != bool(args.counterfactual_dsn):
        parser.error("Supply both PostgreSQL snapshot DSNs, or use SQLite for both.")
    run(args.out, args.dsn, args.counterfactual_dsn, tuple(args.provider))


if __name__ == "__main__":
    main()
