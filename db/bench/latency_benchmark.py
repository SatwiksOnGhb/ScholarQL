"""Measure repeated query latency and p95 under a named database condition."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

QUERIES = {
    "year_venue_authors": (
        """SELECT p.paper_id,p.title,a.name FROM paper p
        JOIN authorship au USING(paper_id) JOIN author a USING(author_id)
        WHERE p.publication_year BETWEEN 2020 AND 2024 AND p.venue_id=%s
        ORDER BY p.publication_year DESC LIMIT 100""",
        ("V-SAMPLE-1",),
    ),
    "top_cited": (
        "SELECT paper_id,title,cited_by_count FROM paper WHERE publication_year >= %s ORDER BY cited_by_count DESC LIMIT 50",
        (2020,),
    ),
    "citation_chain": ("SELECT * FROM citation_chain(%s,%s)", ("P-SAMPLE-1", 3)),
    "fuzzy_author": (
        "SELECT author_id,name FROM author WHERE name % %s ORDER BY similarity(name,%s) DESC LIMIT 10",
        ("Ada Exampel", "Ada Exampel"),
    ),
    "topic_aggregation": (
        """SELECT t.topic_id,p.publication_year,count(DISTINCT p.paper_id)
        FROM paper p JOIN paper_topic pt USING(paper_id) JOIN topic t USING(topic_id)
        GROUP BY t.topic_id,p.publication_year""",
        (),
    ),
    "topic_materialized_view": (
        "SELECT topic_id,topic_name,publication_year,paper_count FROM topic_year_trends",
        (),
    ),
    "author_publication_counts": (
        """SELECT a.author_id,a.name,count(*) FROM author a
        JOIN authorship au USING(author_id) JOIN paper p USING(paper_id)
        WHERE p.publication_year >= %s GROUP BY a.author_id,a.name ORDER BY count(*) DESC LIMIT 50""",
        (2020,),
    ),
    "doi_lookup": ("SELECT paper_id,title FROM paper WHERE doi=%s", ("10.0000/example",)),
    "incoming_citations": ("SELECT citing_id FROM citation WHERE cited_id=%s", ("P-SAMPLE-1",)),
    "institution_collaborations": (
        """SELECT i.institution_id,i.name,count(DISTINCT aa.paper_id)
        FROM institution i JOIN author_affiliation aa USING(institution_id) JOIN paper p USING(paper_id)
        WHERE p.publication_year >= %s GROUP BY i.institution_id,i.name
        ORDER BY count(DISTINCT aa.paper_id) DESC LIMIT 30""",
        (2020,),
    ),
    "venue_year_totals": (
        """SELECT v.venue_id,v.name,p.publication_year,count(*) FROM paper p
        JOIN venue v USING(venue_id) WHERE p.publication_year BETWEEN %s AND %s
        GROUP BY v.venue_id,v.name,p.publication_year ORDER BY count(*) DESC LIMIT 100""",
        (2020, 2024),
    ),
}


def percentile95(samples: list[float]) -> float:
    ordered = sorted(samples)
    index = max(0, min(len(ordered) - 1, int(0.95 * len(ordered) + 0.999999) - 1))
    return ordered[index]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, help="For example baseline or indexed")
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--out", type=Path, default=Path("data/performance_results.jsonl"))
    args = parser.parse_args()
    if args.runs < 5:
        parser.error("Use at least five timed runs; 30 is recommended")
    dsn = os.environ["DATABASE_URL"]
    results = []
    with psycopg.connect(dsn) as connection, connection.cursor() as cursor:
        for name, (sql, params) in QUERIES.items():
            cursor.execute(sql, params)  # warm-up
            samples = []
            for _ in range(args.runs):
                started = time.perf_counter()
                cursor.execute(sql, params)
                cursor.fetchall()
                samples.append((time.perf_counter() - started) * 1000)
            results.append(
                {
                    "label": args.label,
                    "query": name,
                    "runs": args.runs,
                    "median_ms": round(statistics.median(samples), 3),
                    "p95_ms": round(percentile95(samples), 3),
                    "database": connection.info.dbname,
                }
            )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("a", encoding="utf-8") as output:
        for item in results:
            output.write(json.dumps(item) + "\n")
    for item in results:
        print(
            f"{item['label']} {item['query']}: median {item['median_ms']} ms; p95 {item['p95_ms']} ms"
        )


if __name__ == "__main__":
    main()
