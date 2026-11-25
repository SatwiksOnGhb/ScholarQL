"""Copy the embedded papers and author profiles from local MongoDB to Atlas.

Much faster than embedding everything again against Atlas: the vectors are copied as they
are. Run it after pipeline/harvest.py (or the embedding jobs) has finished locally.

Steps:
  1. Drops paper_content, author_profiles and sample_paper_meta on Atlas (old dry-run data)
  2. Recreates them with the $jsonSchema validators (mongo/init/01-collections.js, run with
     mongosh inside the local mongodb container)
  3. Copies every document in batches
  4. Creates the two vector indexes on Atlas and waits until they're ready

Put the Atlas connection string in the repo-root .env (never commit it):
    ATLAS_MONGODB_URI=mongodb+srv://USER:PASSWORD@cluster.xxxxx.mongodb.net/?retryWrites=true&w=majority

Then, from jobs/ with the Docker stack running:
    uv run python copy_to_atlas.py
    uv run python copy_to_atlas.py --with-logs     # also copy query_logs (real questions)
"""

import argparse
import os
import subprocess
import sys

from bson.binary import Binary, BinaryVectorDtype
from pymongo import MongoClient

from common import REPO_ROOT, batched, ensure_vector_index, load_env_file, mongo_db

COLLECTIONS = ["paper_content", "author_profiles"]
BATCH = 500
QUOTA_MB = 480  # Atlas M0 blocks writes at 512 MB; keep a margin
PACK_SAVING = 3335  # bytes saved per document: 384 doubles in an array -> packed float32


def pack(doc: dict) -> dict:
    """Store the vector as a packed float32 BSON vector (~1.6 KB instead of ~4.9 KB)."""
    emb = doc.get("embedding")
    if isinstance(emb, list):
        doc["embedding"] = Binary.from_vector(emb, BinaryVectorDtype.FLOAT32)
    return doc


def allow_packed_vectors(target, name: str) -> None:
    """Let the validator accept the packed vector (binData) as well as an array."""
    info = next(target.list_collections(filter={"name": name}))
    validator = info["options"]["validator"]
    validator["$jsonSchema"]["properties"]["embedding"]["bsonType"] = ["array", "binData"]
    target.command("collMod", name, validator=validator)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--with-logs", action="store_true", help="also copy query_logs")
    args = parser.parse_args()

    load_env_file()
    uri = os.environ.get("ATLAS_MONGODB_URI")
    if not uri:
        sys.exit("Set ATLAS_MONGODB_URI in .env (see the top of this file).")
    db_name = os.environ.get("MONGODB_DB", "scholarql")

    source = mongo_db()  # local Docker MongoDB
    counts = {c: source[c].count_documents({}) for c in COLLECTIONS}
    if not counts["paper_content"]:
        sys.exit("Local paper_content is empty. Run the harvest / embedding jobs first.")
    print("Local:", ", ".join(f"{c} {n}" for c, n in counts.items()), flush=True)

    # Estimate the size on Atlas before writing anything
    estimate = 0.0
    for name in COLLECTIONS:
        stats = source.command("collStats", name)
        estimate += stats["count"] * max(stats.get("avgObjSize", 0) - PACK_SAVING, 0) / 1e6
    print(f"Estimated size on Atlas: ~{estimate:.0f} MB (limit {QUOTA_MB} MB)", flush=True)
    if estimate > QUOTA_MB:
        sys.exit("Too big for the free tier; nothing was written.")

    target_client = MongoClient(uri, serverSelectionTimeoutMS=10_000)
    target_client.admin.command("ping")
    target = target_client[db_name]

    copy = COLLECTIONS + (["query_logs"] if args.with_logs else [])
    for name in copy + ["sample_paper_meta"]:
        target[name].drop()
    print("Dropped the old collections on Atlas", flush=True)

    # Validators and regular indexes, from the same script Docker runs locally
    result = subprocess.run(
        [
            "docker", "compose", "exec", "-T", "-e", f"MONGODB_DB={db_name}", "mongodb",
            "mongosh", uri, "--quiet", "/docker-entrypoint-initdb.d/01-collections.js",
        ],
        cwd=REPO_ROOT,
    )  # fmt: skip
    if result.returncode != 0:
        sys.exit("Couldn't create the collections on Atlas (see the error above).")
    for name in COLLECTIONS:
        allow_packed_vectors(target, name)

    for name in copy:
        total = source[name].count_documents({})
        done = 0
        for batch in batched(source[name].find({}), BATCH):
            target[name].insert_many([pack(d) for d in batch], ordered=False)
            done += len(batch)
            print(f"  {name}: {done}/{total}", end="\r", flush=True)
        print(f"  {name}: {done}/{total} copied      ", flush=True)

    for name in COLLECTIONS:
        ensure_vector_index(target, name)
    print("Done. Atlas has the same papers and vectors as your local MongoDB.")


if __name__ == "__main__":
    main()
