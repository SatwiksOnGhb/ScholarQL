"""Benchmark a fixed 50K-paper workload on the supplied native PostgreSQL schema."""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
from pathlib import Path
from random import Random
from statistics import median
from time import perf_counter

import numpy as np
import psycopg
from scholarql.config import ROOT

from .bootstrap import ensure_schema

SQL_DIR = ROOT.parent / "db" / "bench"
CASES = {
    "venue_year_join": """SELECT p.paper_id, p.title, au.author_id FROM paper p JOIN authorship au USING (paper_id)
        WHERE p.venue_id='V35' AND p.publication_year BETWEEN 2021 AND 2022
        ORDER BY p.publication_year, p.paper_id, au.author_id LIMIT 100""",
    "citation_ranking": """SELECT paper_id,title,cited_by_count FROM paper WHERE publication_year>=2020
        ORDER BY cited_by_count DESC,paper_id LIMIT 50""",
    "recursive_citations": """SELECT level,citing_id,cited_id FROM citation_chain('P47981',3)
        ORDER BY level,citing_id,cited_id""",
    "fuzzy_author": """SELECT author_id,name FROM author WHERE name % 'Samara Quasra'
        ORDER BY similarity(name,'Samara Quasra') DESC, author_id LIMIT 10""",
    "topic_trend_base": """SELECT pt.topic_id,t.name,p.publication_year,count(DISTINCT p.paper_id)
        FROM paper p JOIN paper_topic pt USING(paper_id) JOIN topic t USING(topic_id)
        GROUP BY pt.topic_id,t.name,p.publication_year ORDER BY pt.topic_id,p.publication_year""",
    "topic_trend_view": """SELECT topic_id,topic_name,publication_year,paper_count FROM topic_year_trends
        ORDER BY topic_id,publication_year""",
    "author_papers": """SELECT p.paper_id,p.title FROM authorship a JOIN paper p USING(paper_id)
        WHERE a.author_id='A9001' ORDER BY p.paper_id""",
    "doi_lookup": """SELECT paper_id,title FROM paper WHERE doi='10.0000/study.27983'""",
    "incoming_citations": """SELECT c.citing_id,p.title FROM citation c JOIN paper p ON p.paper_id=c.citing_id
        WHERE c.cited_id='P8' ORDER BY c.citing_id LIMIT 60""",
    "title_contains": """SELECT paper_id,title FROM paper WHERE title ILIKE '%quasar%'
        ORDER BY paper_id LIMIT 50""",
}


def write_csv(path: Path, rows: list[dict]):
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def prepare(conn):
    ensure_schema(conn)
    marker = conn.execute("SELECT to_regclass('public.scholarql_index_fixture')").fetchone()[0]
    if not marker:
        if conn.execute("SELECT EXISTS (SELECT 1 FROM paper)").fetchone()[0]:
            raise ValueError("Create a separate empty database before running the synthetic study.")
        conn.execute((SQL_DIR / "scale_fixture.sql").read_text(), prepare=False)
    if conn.execute("SELECT version,paper_count FROM scholarql_index_fixture").fetchall() != [
        (1, 50000)
    ]:
        raise ValueError("Experiment fixture version or scale differs.")
    counts = {
        table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in ("paper", "citation", "author", "venue", "authorship", "paper_topic")
    }
    if counts["paper"] != 50_000:
        raise ValueError("Experiment expects exactly 50,000 synthetic papers.")
    return counts


def run(dsn: str, out: Path, repeats: int):
    out.mkdir(parents=True, exist_ok=True)
    measurements, plans, denotations = [], {}, {}
    with psycopg.connect(dsn) as conn:
        counts = prepare(conn)
        version = conn.execute("SELECT version()").fetchone()[0]
        settings = dict(
            conn.execute("""SELECT name, setting FROM pg_settings WHERE name IN
            ('shared_buffers','effective_cache_size','work_mem','jit','max_parallel_workers_per_gather')""").fetchall()
        )
        conn.commit()
        try:
            for block, condition in enumerate(("baseline", "indexed", "indexed", "baseline"), 1):
                print(f"PostgreSQL index study block {block}: {condition}", flush=True)
                name = (
                    "with_secondary_indexes.sql"
                    if condition == "indexed"
                    else "without_secondary_indexes.sql"
                )
                conn.execute((SQL_DIR / name).read_text(), prepare=False)
                conn.execute("ANALYZE")
                conn.commit()
                conn.execute("SET LOCAL jit=off")
                conn.execute("SET LOCAL max_parallel_workers_per_gather=0")
                for query_name, sql in CASES.items():
                    rows = conn.execute(sql, prepare=False).fetchall()
                    if rows != denotations.setdefault(query_name, rows):
                        raise ValueError(f"Index conditions changed the result for {query_name}.")
                    for _ in range(3):
                        conn.execute(sql, prepare=False).fetchall()
                    if (condition, query_name) not in plans:
                        plans[condition, query_name] = conn.execute(
                            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, prepare=False
                        ).fetchone()[0][0]
                random = Random(34719 + block)
                keys = list(CASES)
                for repeat in range(1, repeats + 1):
                    random.shuffle(keys)
                    for query_name in keys:
                        started = perf_counter()
                        rows = conn.execute(CASES[query_name], prepare=False).fetchall()
                        measured_ms = (perf_counter() - started) * 1000
                        measurements.append(
                            {
                                "query": query_name,
                                "condition": condition,
                                "block": block,
                                "rep": repeat,
                                "client_ms": round(measured_ms, 6),
                                "rows": len(rows),
                            }
                        )
                conn.commit()
        finally:
            conn.rollback()
            conn.execute((SQL_DIR / "with_secondary_indexes.sql").read_text(), prepare=False)
            conn.commit()
    summary = []
    if denotations["topic_trend_base"] != denotations["topic_trend_view"]:
        raise ValueError("The materialized trend view does not match the base aggregation.")
    for key in CASES:
        a, b = (
            [
                row["client_ms"]
                for row in measurements
                if row["query"] == key and row["condition"] == cond
            ]
            for cond in ("baseline", "indexed")
        )
        base, improved = median(a), median(b)
        pa, pb = (plans[c, key] for c in ("baseline", "indexed"))
        summary.append(
            {
                "query": key,
                "baseline_median_ms": round(base, 4),
                "indexed_median_ms": round(improved, 4),
                "baseline_p95_ms": round(float(np.quantile(a, 0.95)), 4),
                "indexed_p95_ms": round(float(np.quantile(b, 0.95)), 4),
                "speedup": round(base / improved, 3),
                "baseline_plan": pa["Plan"]["Node Type"],
                "indexed_plan": pb["Plan"]["Node Type"],
                "baseline_buffers_hit": pa["Plan"].get("Shared Hit Blocks", 0),
                "indexed_buffers_hit": pb["Plan"].get("Shared Hit Blocks", 0),
                "result_rows": len(denotations[key]),
            }
        )
    cpu = platform.processor() or platform.machine()
    for line in (
        Path("/proc/cpuinfo").read_text().splitlines() if Path("/proc/cpuinfo").exists() else []
    ):
        if line.startswith("model name"):
            cpu = line.split(":", 1)[-1].strip()
            break
    quota_path = Path("/sys/fs/cgroup/cpu.max")
    mem_path = Path("/sys/fs/cgroup/memory.max")
    meta = {
        "postgresql": version,
        "system": platform.platform(),
        "cpu": cpu,
        "logical_cpus": os.cpu_count(),
        "cpu_quota": quota_path.read_text().strip() if quota_path.exists() else None,
        "memory_limit_bytes": mem_path.read_text().strip() if mem_path.exists() else None,
        "counts": counts,
        "settings_server": settings,
        "settings_session": {"jit": "off", "max_parallel_workers_per_gather": 0},
        "repetitions_per_query_and_condition": repeats * 2,
        "fixture": "deterministic synthetic",
        "cache_method": "Warm cache; 3 untimed fetches per block per query; ABBA; shuffled query order within each repeat.",
        "timing": "Client execute and fetchall on same TCP connection, including protocol and conversion; EXPLAIN is separate.",
        "rows_verified_equal_across_conditions": True,
    }
    write_csv(out / "index_summary.csv", summary)
    write_csv(out / "index_timings.csv", measurements)
    (out / "index_plans.json").write_text(
        json.dumps(
            {
                "metadata": meta,
                "cases": CASES,
                "plans": {
                    cond: {key: plans[cond, key] for key in CASES}
                    for cond in ("baseline", "indexed")
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (out / "index_results.json").write_text(
        json.dumps({"metadata": meta, "rows": summary}, indent=2), encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.getenv("SCHOLARQL_INDEX_DSN"))
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    parser.add_argument("--repeats", type=int, default=20, help="Repetitions per query per block.")
    args = parser.parse_args()
    if not args.dsn or args.repeats < 1:
        parser.error("Supply a dedicated --dsn and positive --repeats.")
    run(args.dsn, args.out, args.repeats)


if __name__ == "__main__":
    main()
