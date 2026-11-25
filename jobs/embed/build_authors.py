"""Build author_profiles: one vector per author, the mean of their papers' embeddings.

Run after embed_papers. Authorship and institutions come from A's PostgreSQL tables
(authorship, author, author_affiliation, institution), or from papers_meta.jsonl with --meta.

An author's institution is the one listed on their most recent paper. Authors with no
embedded papers are skipped. Re-running replaces every profile, so it's always in sync.

Usage (from jobs/):  uv run python -m embed.build_authors [--meta path/to/papers_meta.jsonl]
"""

import argparse
import sys
from pathlib import Path

import numpy as np
from pymongo import ReplaceOne

from common import batched, ensure_vector_index, load_meta, mongo_db


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--meta", type=Path, help="papers_meta.jsonl instead of PostgreSQL")
    args = parser.parse_args()

    db = mongo_db()
    vectors = {
        d["_id"]: np.asarray(d["embedding"], dtype=np.float32)
        for d in db.paper_content.find({"embedding": {"$exists": True}}, {"embedding": 1})
    }
    if not vectors:
        sys.exit("No embedded papers in paper_content. Run embed.embed_papers first.")

    # Group papers by author; oldest first, so the last institution seen is the latest
    authors: dict[str, dict] = {}
    for paper in sorted(load_meta(args.meta).values(), key=lambda p: p["year"] or 0):
        if paper["paper_id"] not in vectors:
            continue
        for a in paper["authors"]:
            entry = authors.setdefault(a["author_id"], {"name": a["name"], "paper_ids": []})
            entry["paper_ids"].append(paper["paper_id"])
            if a.get("institution_id") is not None:
                entry["latest_institution"] = a["institution_id"]  # papers are sorted by year

    ops = []
    for author_id, a in authors.items():
        mean = np.mean([vectors[pid] for pid in a["paper_ids"]], axis=0)
        mean /= np.linalg.norm(mean)  # unit length, like the paper vectors
        ops.append(
            ReplaceOne(
                {"_id": author_id},
                {
                    "_id": author_id,
                    "name": a["name"],
                    "institution_id": a.get("latest_institution"),
                    "embedding": [float(x) for x in mean],
                    "paper_ids": a["paper_ids"],
                },
                upsert=True,
            )
        )
    for batch in batched(ops, 500):
        db.author_profiles.bulk_write(batch, ordered=False)

    multi = sum(len(a["paper_ids"]) > 1 for a in authors.values())
    print(f"Built {len(ops)} author profiles ({multi} with 2+ papers)", file=sys.stderr)
    ensure_vector_index(db, "author_profiles")
    print(f"author_profiles: {db.author_profiles.count_documents({})} documents")


if __name__ == "__main__":
    main()
