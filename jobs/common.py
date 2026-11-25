"""Helpers shared by the jobs: settings from .env, MongoDB, the embedding model, vector indexes.

Run jobs as modules from jobs/ so this file is importable, e.g.
    uv run python -m embed.embed_papers
"""

import json
import os
import sys
import time
from collections.abc import Iterable, Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = REPO_ROOT / "data" / "sample"
# B's 353-paper pilot, already loaded into PostgreSQL by db/init (see db/seed/)
PILOT_CONTENT = REPO_ROOT / "db" / "seed" / "pilot_content.jsonl"
VECTOR_INDEXES = REPO_ROOT / "mongo" / "vector-indexes.json"

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384
# Outside the repo on purpose: the repo lives in OneDrive and the model is ~70 MB
MODEL_CACHE = Path.home() / ".cache" / "fastembed"


def load_env_file() -> None:
    """Read the repo-root .env into os.environ, without overriding variables already set."""
    env = REPO_ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and not key.strip().startswith("#"):
            os.environ.setdefault(key.strip(), value.strip())


def mongo_db():
    """The scholarql database, using the same settings as docker-compose (host-side port)."""
    from pymongo import MongoClient

    load_env_file()
    uri = os.environ.get("MONGODB_URI") or (
        f"mongodb://{os.environ.get('MONGO_USER', 'scholarql')}:"
        f"{os.environ.get('MONGO_PASSWORD', 'scholarql')}@localhost:"
        f"{os.environ.get('MONGO_PORT', '27017')}/?directConnection=true"
    )
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")  # fail fast with a clear error if Mongo isn't running
    return client[os.environ.get("MONGODB_DB", "scholarql")]


def postgres_url() -> str:
    """The owner connection to A's database (same defaults as docker-compose, host-side port)."""
    load_env_file()
    return os.environ.get("DATABASE_URL") or (
        f"postgresql://{os.environ.get('POSTGRES_USER', 'scholarql')}:"
        f"{os.environ.get('POSTGRES_PASSWORD', 'scholarql')}@localhost:"
        f"{os.environ.get('POSTGRES_PORT', '5432')}/{os.environ.get('POSTGRES_DB', 'scholarql')}"
    )


def short_openalex_id(value: str) -> str:
    """https://openalex.org/W2741809807 -> W2741809807 (A's primary-key format)."""
    return value.removeprefix("https://openalex.org/").strip()


def load_meta(meta_path: Path | None) -> dict[str, dict]:
    """Per-paper title, year, venue and authors (with institution), keyed by paper_id.

    From A's PostgreSQL tables by default; from a papers_meta.jsonl file (the OpenAlex sample,
    see sample/fetch_openalex.py) when `meta_path` is given.
    """
    if meta_path is not None:
        return {m["paper_id"]: m for m in read_jsonl(meta_path)}

    import psycopg

    meta: dict[str, dict] = {}
    with psycopg.connect(postgres_url(), connect_timeout=5) as conn:
        for pid, title, year, venue_id, venue_name in conn.execute(
            """SELECT p.paper_id, p.title, p.publication_year, p.venue_id, v.name
               FROM paper p LEFT JOIN venue v USING (venue_id)"""
        ):
            meta[pid] = {
                "paper_id": pid,
                "title": title,
                "year": year,
                "venue_id": venue_id,
                "venue_name": venue_name,
                "authors": [],
            }
        # One row per author per paper; their first affiliation on that paper's byline
        for pid, author_id, name, inst_id, inst_name in conn.execute(
            """SELECT au.paper_id, au.author_id, a.name, aff.institution_id, i.name
               FROM authorship au
               JOIN author a USING (author_id)
               LEFT JOIN LATERAL (
                   SELECT institution_id FROM author_affiliation af
                   WHERE af.paper_id = au.paper_id AND af.author_id = au.author_id
                   ORDER BY institution_id LIMIT 1
               ) aff ON true
               LEFT JOIN institution i ON i.institution_id = aff.institution_id
               ORDER BY au.paper_id, au.author_order"""
        ):
            if pid in meta:
                meta[pid]["authors"].append(
                    {
                        "author_id": author_id,
                        "name": name,
                        "institution_id": inst_id,
                        "institution_name": inst_name,
                    }
                )
    if not meta:
        sys.exit("No papers in PostgreSQL. Load A's data first, or pass --meta <file>.")
    return meta


def embedding_model():
    # Windows without Developer Mode can't symlink; the cache still works, so skip the warning
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    from fastembed import TextEmbedding

    MODEL_CACHE.mkdir(parents=True, exist_ok=True)
    return TextEmbedding(EMBEDDING_MODEL, cache_dir=str(MODEL_CACHE))


def read_jsonl(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def batched(items: Iterable, size: int) -> Iterator[list]:
    batch = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def ensure_vector_index(db, collection: str, timeout_s: int = 300) -> None:
    """Create or update the index defined in mongo/vector-indexes.json; wait until ready."""
    from pymongo.operations import SearchIndexModel

    spec = next(s for s in json.loads(VECTOR_INDEXES.read_text()) if s["collection"] == collection)
    coll = db[collection]
    existing = {i["name"]: i for i in coll.list_search_indexes()}
    current = existing.get(spec["name"])
    if current is None:
        coll.create_search_index(
            SearchIndexModel(definition=spec["definition"], name=spec["name"], type=spec["type"])
        )
        print(f"Creating vector index {collection}.{spec['name']}", file=sys.stderr)
    elif current.get("latestDefinition") != spec["definition"]:
        coll.update_search_index(spec["name"], spec["definition"])
        print(f"Updating vector index {collection}.{spec['name']}", file=sys.stderr)

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        index = next(coll.list_search_indexes(spec["name"]), None)
        if index and index.get("queryable") and index.get("status") == "READY":
            print(f"Vector index {collection}.{spec['name']} is ready", file=sys.stderr)
            return
        time.sleep(2)
    raise TimeoutError(f"Vector index {spec['name']} not ready after {timeout_s}s")
