"""Load fetched OpenAlex JSONL into the relational schema in safe batches."""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BATCH_SIZE = 500


def short_id(value: str | None) -> str | None:
    if not value:
        return None
    return value.removeprefix("https://openalex.org/").strip() or None


def doi_value(value: str | None) -> str | None:
    if not value:
        return None
    return (
        value.removeprefix("https://doi.org/").removeprefix("http://doi.org/").strip().lower()
        or None
    )


def arxiv_value(work: dict[str, Any]) -> str | None:
    raw = (work.get("ids") or {}).get("arxiv")
    if raw:
        value = raw.removeprefix("https://arxiv.org/abs/").removeprefix("http://arxiv.org/abs/")
        return re.sub(r"v\d+$", "", value)
    doi = doi_value(work.get("doi"))
    if doi and doi.lower().startswith("10.48550/arxiv."):
        return re.sub(r"v\d+$", "", doi.split(".", 2)[-1])
    return None


def venue_type(source: dict[str, Any]) -> str:
    value = (source.get("type") or "").lower()
    if "conference" in value:
        return "conference"
    if "journal" in value:
        return "journal"
    if "repository" in value:
        return "repository"
    if "book" in value or "series" in value:
        return "book_series"
    return "unknown"


def topic_rows(topic: dict[str, Any] | None) -> list[tuple[int, dict[str, Any]]]:
    if not topic:
        return []
    result: list[tuple[int, dict[str, Any]]] = []
    subfield = topic.get("subfield")
    subfield_field = (subfield or {}).get("field") or {}
    field = topic.get("field") or subfield_field
    domain = topic.get("domain") or field.get("domain")
    if domain and domain.get("id"):
        result.append(
            (
                0,
                {
                    "topic_id": short_id(domain["id"]),
                    "name": domain.get("display_name") or domain.get("name") or "Unknown domain",
                    "parent_topic_id": None,
                    "level": 0,
                },
            )
        )
    if field and field.get("id"):
        result.append(
            (
                1,
                {
                    "topic_id": short_id(field["id"]),
                    "name": field.get("display_name") or field.get("name") or "Unknown field",
                    "parent_topic_id": short_id(domain.get("id")) if domain else None,
                    "level": 1,
                },
            )
        )
    if subfield and subfield.get("id"):
        result.append(
            (
                2,
                {
                    "topic_id": short_id(subfield["id"]),
                    "name": subfield.get("display_name")
                    or subfield.get("name")
                    or "Unknown subfield",
                    "parent_topic_id": short_id(field.get("id")) if field else None,
                    "level": 2,
                },
            )
        )
    if topic.get("id"):
        result.append(
            (
                3,
                {
                    "topic_id": short_id(topic["id"]),
                    "name": topic.get("display_name") or topic.get("name") or "Unknown topic",
                    "parent_topic_id": short_id(subfield.get("id")) if subfield else None,
                    "level": 3,
                },
            )
        )
    return result


def load_batch(connection: psycopg.Connection, works: list[dict[str, Any]]) -> None:
    venues: dict[str, tuple[Any, ...]] = {}
    institutions: dict[str, tuple[Any, ...]] = {}
    authors: dict[str, tuple[Any, ...]] = {}
    papers: dict[str, tuple[Any, ...]] = {}
    authorships: dict[tuple[str, str], tuple[Any, ...]] = {}
    affiliations: set[tuple[str, str, str]] = set()
    topics_by_level: dict[int, dict[str, tuple[Any, ...]]] = defaultdict(dict)
    paper_topics: dict[tuple[str, str], tuple[Any, ...]] = {}

    for work in works:
        paper_id = short_id(work.get("id"))
        title = (work.get("title") or "").strip()
        if not paper_id or not title:
            continue

        location = work.get("primary_location") or {}
        source = location.get("source") or {}
        venue_id = short_id(source.get("id"))
        if venue_id and source.get("display_name"):
            venues[venue_id] = (venue_id, source["display_name"], venue_type(source), None)

        papers[paper_id] = (
            paper_id,
            title,
            work.get("publication_year"),
            work.get("publication_date"),
            arxiv_value(work),
            doi_value(work.get("doi")),
            venue_id,
            0,
            0.0,
            work.get("updated_date"),
        )

        primary_topic_id = short_id((work.get("primary_topic") or {}).get("id"))
        for topic in work.get("topics") or []:
            for level, item in topic_rows(topic):
                if item["topic_id"]:
                    topics_by_level[level][item["topic_id"]] = (
                        item["topic_id"],
                        item["name"],
                        item["parent_topic_id"],
                        item["level"],
                    )
            topic_id = short_id(topic.get("id"))
            if topic_id:
                score = topic.get("score")
                paper_topics[(paper_id, topic_id)] = (
                    paper_id,
                    topic_id,
                    float(score) if score is not None else None,
                    topic_id == primary_topic_id,
                )
        # Some records have a primary topic but omit it from the general topics array.
        primary = work.get("primary_topic")
        for level, item in topic_rows(primary):
            if item["topic_id"]:
                topics_by_level[level][item["topic_id"]] = (
                    item["topic_id"],
                    item["name"],
                    item["parent_topic_id"],
                    item["level"],
                )
        if primary_topic_id and (paper_id, primary_topic_id) not in paper_topics:
            paper_topics[(paper_id, primary_topic_id)] = (paper_id, primary_topic_id, None, True)

        # Retain arXiv membership separately from OpenAlex's taxonomy.
        for category in (work.get("scholarql_arxiv", {}).get("categories") or "").split("|"):
            if not category:
                continue
            topics_by_level[1][category] = (category, category, None, 1)
            paper_topics[(paper_id, category)] = (paper_id, category, None, False)

        for order, authorship in enumerate(work.get("authorships") or [], start=1):
            author = authorship.get("author") or {}
            author_id = short_id(author.get("id"))
            author_name = (author.get("display_name") or "").strip()
            if not author_id or not author_name:
                continue
            authors[author_id] = (author_id, author_name, None, None)
            authorships[(paper_id, author_id)] = (paper_id, author_id, order)
            for institution in authorship.get("institutions") or []:
                institution_id = short_id(institution.get("id"))
                institution_name = (institution.get("display_name") or "").strip()
                if not institution_id or not institution_name:
                    continue
                institutions[institution_id] = (
                    institution_id,
                    institution_name,
                    institution.get("country_code"),
                    (institution.get("ids") or {}).get("ror"),
                )
                affiliations.add((paper_id, author_id, institution_id))

    with connection.cursor() as cursor:
        if venues:
            cursor.executemany(
                """INSERT INTO venue (venue_id,name,venue_type,issn) VALUES (%s,%s,%s,%s)
                   ON CONFLICT (venue_id) DO UPDATE SET name=EXCLUDED.name, venue_type=EXCLUDED.venue_type""",
                venues.values(),
            )
        if institutions:
            cursor.executemany(
                """INSERT INTO institution (institution_id,name,country_code,ror_id) VALUES (%s,%s,%s,%s)
                   ON CONFLICT (institution_id) DO UPDATE SET name=EXCLUDED.name,country_code=EXCLUDED.country_code,
                     ror_id=coalesce(EXCLUDED.ror_id,institution.ror_id)""",
                institutions.values(),
            )
        if authors:
            cursor.executemany(
                """INSERT INTO author (author_id,name,orcid,h_index) VALUES (%s,%s,%s,%s)
                   ON CONFLICT (author_id) DO UPDATE SET name=EXCLUDED.name""",
                authors.values(),
            )
        for level in sorted(topics_by_level):
            cursor.executemany(
                """INSERT INTO topic (topic_id,name,parent_topic_id,level) VALUES (%s,%s,%s,%s)
                   ON CONFLICT (topic_id) DO UPDATE SET name=EXCLUDED.name,
                     parent_topic_id=coalesce(EXCLUDED.parent_topic_id,topic.parent_topic_id), level=EXCLUDED.level""",
                topics_by_level[level].values(),
            )
        if papers:
            cursor.executemany(
                """INSERT INTO paper (paper_id,title,publication_year,publication_date,arxiv_id,doi,venue_id,cited_by_count,pagerank_score,openalex_updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (paper_id) DO UPDATE SET title=EXCLUDED.title,
                     publication_year=EXCLUDED.publication_year, publication_date=EXCLUDED.publication_date,
                     arxiv_id=coalesce(EXCLUDED.arxiv_id,paper.arxiv_id), doi=coalesce(EXCLUDED.doi,paper.doi),
                     venue_id=coalesce(EXCLUDED.venue_id,paper.venue_id), openalex_updated_at=EXCLUDED.openalex_updated_at""",
                papers.values(),
            )
        if authorships:
            cursor.executemany(
                """INSERT INTO authorship (paper_id,author_id,author_order) VALUES (%s,%s,%s)
                   ON CONFLICT (paper_id,author_id) DO UPDATE SET author_order=EXCLUDED.author_order""",
                authorships.values(),
            )
        if affiliations:
            cursor.executemany(
                "INSERT INTO author_affiliation (paper_id,author_id,institution_id) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                affiliations,
            )
        if paper_topics:
            cursor.executemany(
                """INSERT INTO paper_topic (paper_id,topic_id,relevance,is_primary) VALUES (%s,%s,%s,%s)
                   ON CONFLICT (paper_id,topic_id) DO UPDATE SET relevance=coalesce(EXCLUDED.relevance,paper_topic.relevance),
                     is_primary=EXCLUDED.is_primary""",
                paper_topics.values(),
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSONL generated by fetch_openalex.py")
    parser.add_argument(
        "--semantic-scholar",
        type=Path,
        help="Optional enrichment JSONL from enrich_semantic_scholar.py",
    )
    parser.add_argument(
        "--skip-ranking",
        action="store_true",
        help="Do not run the PageRank procedure after loading",
    )
    args = parser.parse_args()
    dsn = os.environ["DATABASE_URL"]
    all_paper_ids: set[str] = set()
    arxiv_to_paper: dict[str, str] = {}
    doi_to_paper: dict[str, str] = {}
    for line in args.input.open(encoding="utf-8"):
        row = json.loads(line)
        paper_id = short_id(row.get("id"))
        if paper_id:
            all_paper_ids.add(paper_id)
            arxiv = arxiv_value(row)
            doi = doi_value(row.get("doi"))
            if arxiv:
                arxiv_to_paper[arxiv] = paper_id
            if doi:
                doi_to_paper[doi] = paper_id

    with psycopg.connect(dsn) as connection:
        batch: list[dict[str, Any]] = []
        loaded = 0
        for line in args.input.open(encoding="utf-8"):
            batch.append(json.loads(line))
            if len(batch) >= BATCH_SIZE:
                with connection.transaction():
                    load_batch(connection, batch)
                loaded += len(batch)
                print(f"Loaded {loaded} work records")
                batch.clear()
        if batch:
            with connection.transaction():
                load_batch(connection, batch)
            loaded += len(batch)
            print(f"Loaded {loaded} work records")

        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute(
                    "CREATE TEMP TABLE citation_stage (citing_id text, cited_id text, source text) ON COMMIT DROP"
                )
                with cursor.copy(
                    "COPY citation_stage (citing_id,cited_id,source) FROM STDIN"
                ) as copy:
                    for line in args.input.open(encoding="utf-8"):
                        work = json.loads(line)
                        citing_id = short_id(work.get("id"))
                        if not citing_id:
                            continue
                        for cited in work.get("referenced_works") or []:
                            cited_id = short_id(cited)
                            if cited_id in all_paper_ids and cited_id != citing_id:
                                copy.write_row((citing_id, cited_id, "openalex"))
                    if args.semantic_scholar:
                        for line in args.semantic_scholar.open(encoding="utf-8"):
                            record = json.loads(line)
                            citing_id = short_id(record.get("openalex_id"))
                            if citing_id not in all_paper_ids:
                                citing_id = arxiv_to_paper.get(
                                    re.sub(r"v\d+$", "", record.get("arxiv_id") or "")
                                )
                            if not citing_id:
                                continue
                            for reference in record.get("references") or []:
                                external = reference.get("external_ids") or {}
                                target = None
                                if external.get("ArXiv"):
                                    target = arxiv_to_paper.get(
                                        re.sub(r"v\d+$", "", external["ArXiv"])
                                    )
                                if not target and external.get("DOI"):
                                    target = doi_to_paper.get(doi_value(external["DOI"]) or "")
                                if target in all_paper_ids and target != citing_id:
                                    copy.write_row((citing_id, target, "semantic_scholar"))
                cursor.execute(
                    """INSERT INTO citation (citing_id,cited_id,source)
                       SELECT DISTINCT s.citing_id,s.cited_id,s.source FROM citation_stage s
                       JOIN paper src ON src.paper_id=s.citing_id
                       JOIN paper dst ON dst.paper_id=s.cited_id
                       ON CONFLICT (citing_id,cited_id) DO NOTHING"""
                )
                cursor.execute("ANALYZE")
                if not args.skip_ranking:
                    cursor.execute("CALL compute_pagerank(30, 0.85)")
                cursor.execute("CALL refresh_analytics()")
        print(f"Loaded {loaded} works and recomputed in-scope citations and analytics")


if __name__ == "__main__":
    main()
