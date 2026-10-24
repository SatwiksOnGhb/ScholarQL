"""Embed paper abstracts into MongoDB paper_content, then make sure the vector index exists.

Input: papers_content.jsonl ({"paper_id", "abstract", "tldr"}) from A's pipeline, plus
title/year/venue_id per paper. Until A's PostgreSQL is loaded those come from the sample
papers_meta.jsonl. TODO(A): read title, year, venue_id from the paper table instead.

Papers that already have an embedding are skipped, so the job can be re-run or resumed
(use --force to re-embed everything).

Usage (from jobs/):
    uv run python -m embed.embed_papers
    uv run python -m embed.embed_papers --content path/to/papers_content.jsonl --meta ...
"""

import argparse
import sys
import time
from pathlib import Path

from pymongo import ReplaceOne, UpdateOne

from common import (
    EMBEDDING_DIM,
    SAMPLE_DIR,
    batched,
    embedding_model,
    ensure_vector_index,
    mongo_db,
    read_jsonl,
)

BATCH = 64


def document_text(title: str | None, abstract: str) -> str:
    # The title carries a lot of the topic signal, so embed it with the abstract
    return f"{title}. {abstract}" if title else abstract


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--content", type=Path, default=SAMPLE_DIR / "papers_content.jsonl")
    parser.add_argument("--meta", type=Path, default=SAMPLE_DIR / "papers_meta.jsonl")
    parser.add_argument("--force", action="store_true", help="re-embed papers that have vectors")
    args = parser.parse_args()

    db = mongo_db()
    meta = {m["paper_id"]: m for m in read_jsonl(args.meta)}  # TODO(A): from PostgreSQL
    done = (
        set()
        if args.force
        else {d["_id"] for d in db.paper_content.find({"embedding": {"$exists": True}}, {"_id": 1})}
    )

    todo, missing_meta = [], 0
    for paper in read_jsonl(args.content):
        pid = paper["paper_id"]
        if pid in done or not paper.get("abstract"):
            continue
        if pid not in meta:
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
    upload_sample_meta(db, meta)


def upload_sample_meta(db, meta: dict[int, dict]) -> None:
    """TEMPORARY (TODO(A)): copy titles, venues and institutions into a scratch collection.

    The API reads paper titles from A's PostgreSQL tables. Until those exist, it falls back to
    `sample_paper_meta` so search and reviewer results show real titles, locally and when
    deployed. Drop the collection once A's data is loaded:  db.sample_paper_meta.drop()
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
