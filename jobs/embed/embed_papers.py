"""Embed paper abstracts into MongoDB paper_content, then make sure the vector index exists.

Input: papers_content.jsonl ({"paper_id", "abstract", "tldr"}) from A's pipeline
(pipeline/extract_papers_content.py) or the pilot seed (db/seed/pilot_content.jsonl, the
default), plus title/year/venue_id per paper from A's PostgreSQL tables. Without PostgreSQL,
pass the OpenAlex sample's papers_meta.jsonl with --meta.

Papers that already have an embedding are skipped, so the job can be re-run or resumed
(use --force to re-embed everything).

Usage (from jobs/):
    uv run python -m embed.embed_papers                       # pilot, metadata from PostgreSQL
    uv run python -m embed.embed_papers --content ../data/papers_content.jsonl   # A's full set
    uv run python -m embed.embed_papers --content ../data/sample/papers_content.jsonl \
        --meta ../data/sample/papers_meta.jsonl                # OpenAlex sample, no PostgreSQL
"""

import argparse
import sys
import time
from pathlib import Path

from pymongo import ReplaceOne, UpdateOne

from common import (
    EMBEDDING_DIM,
    PILOT_CONTENT,
    batched,
    embedding_model,
    ensure_vector_index,
    load_meta,
    mongo_db,
    read_jsonl,
    short_openalex_id,
)

BATCH = 64


def document_text(title: str | None, abstract: str) -> str:
    # The title carries a lot of the topic signal, so embed it with the abstract
    return f"{title}. {abstract}" if title else abstract


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--content", type=Path, default=PILOT_CONTENT)
    parser.add_argument("--meta", type=Path, help="papers_meta.jsonl instead of PostgreSQL")
    parser.add_argument("--force", action="store_true", help="re-embed papers that have vectors")
    args = parser.parse_args()

    db = mongo_db()
    meta = load_meta(args.meta)
    done = (
        set()
        if args.force
        else {d["_id"] for d in db.paper_content.find({"embedding": {"$exists": True}}, {"_id": 1})}
    )

    todo, missing_meta = [], 0
    for paper in read_jsonl(args.content):
        pid = paper["paper_id"] = short_openalex_id(str(paper["paper_id"]))
        if pid in done or not paper.get("abstract"):
            continue
        if pid not in meta or meta[pid].get("year") is None:
            missing_meta += 1  # no year -> can't satisfy the paper_content validator
            continue
        todo.append(paper)
    print(
        f"{len(todo)} papers to embed ({len(done)} already done, {missing_meta} without metadata)",
        file=sys.stderr,
    )

    if todo:
        model = embedding_model()
        start = time.perf_counter()
        for i, batch in enumerate(batched(todo, BATCH)):
            texts = [document_text(meta[p["paper_id"]].get("title"), p["abstract"]) for p in batch]
            vectors = list(model.passage_embed(texts, batch_size=BATCH))
            ops = []
            for paper, vector in zip(batch, vectors, strict=True):
                assert len(vector) == EMBEDDING_DIM
                m = meta[paper["paper_id"]]
                ops.append(
                    UpdateOne(
                        {"_id": paper["paper_id"]},
                        {
                            "$set": {
                                "abstract": paper["abstract"],
                                "tldr": paper.get("tldr"),
                                "embedding": [float(x) for x in vector],
                                "year": m["year"],
                                "venue_id": m.get("venue_id"),
                            }
                        },
                        upsert=True,
                    )
                )
            db.paper_content.bulk_write(ops, ordered=False)
            print(f"  {min((i + 1) * BATCH, len(todo))}/{len(todo)}", file=sys.stderr)
        rate = len(todo) / (time.perf_counter() - start)
        print(f"Embedded {len(todo)} papers ({rate:.0f}/s)", file=sys.stderr)

    ensure_vector_index(db, "paper_content")
    print(f"paper_content: {db.paper_content.count_documents({})} documents")
    if args.meta is not None:  # no PostgreSQL: the API reads titles from here instead
        upload_sample_meta(db, meta)


def upload_sample_meta(db, meta: dict[int, dict]) -> None:
    """Copy titles, venues and institutions into `sample_paper_meta` (only with --meta).

    The API reads paper titles from A's PostgreSQL tables and falls back to this collection
    when PostgreSQL has none, so the OpenAlex sample works without it.
    """
    ops = []
    for pid, m in meta.items():
        institutions = {
            a["institution_id"]: a["institution_name"]
            for a in m.get("authors", [])
            if a.get("institution_id") is not None and a.get("institution_name")
        }
        doc = {
            "_id": pid,
            "title": m["title"],
            "year": m.get("year"),
            "venue_id": m.get("venue_id"),
            "venue_name": m.get("venue_name"),
            "institutions": [{"institution_id": i, "name": n} for i, n in institutions.items()],
        }
        ops.append(ReplaceOne({"_id": pid}, doc, upsert=True))
    for batch in batched(ops, 500):
        db.sample_paper_meta.bulk_write(batch, ordered=False)
    db.sample_paper_meta.create_index("institutions.institution_id")
    print(f"sample_paper_meta: {db.sample_paper_meta.count_documents({})} documents (temporary)")


if __name__ == "__main__":
    main()
