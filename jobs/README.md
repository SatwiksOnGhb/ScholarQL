# jobs/ (owned by Person C)

Offline scripts that prepare data. They run on your machine (not in Docker) with their own
uv project, so heavy dependencies like fastembed stay out of the API image. Run them as
modules from `jobs/` so they can share `common.py`:

```bash
cd jobs
uv sync
```

The Docker stack must be running (`docker compose up`); jobs connect to MongoDB on
`localhost:27017` using the same settings as `.env`.

## 1. Sample data (until A's ingest is ready)

```bash
uv run python -m sample.fetch_openalex            # 500 papers -> ../data/sample/
uv run python -m sample.fetch_openalex --n 2000   # more
```

Writes to `data/sample/` (gitignored; re-run to recreate):

- `papers_content.jsonl`: `{"paper_id", "abstract", "tldr"}`, the same format A's pipeline
  will produce. `tldr` is null here (TLDRs come from A's Semantic Scholar step).
- `papers_meta.jsonl`: title, year, venue and authors with institutions; a stand-in for
  A's PostgreSQL tables. `# TODO(A)`: read these from the database once it's loaded.

No API key is needed for a few thousand papers. Beyond 10,000 results OpenAlex requires one:
get a free key at https://openalex.org/settings/api and set `OPENALEX_API_KEY` in `.env`.

## 2. Embeddings and author profiles

```bash
uv run python -m embed.embed_papers    # papers -> MongoDB paper_content + vector index
uv run python -m embed.build_authors   # author_profiles (mean of their papers) + vector index
```

- Model: `BAAI/bge-small-en-v1.5` via fastembed (384 dims, CPU). Downloaded once (~65 MB) to
  `~/.cache/fastembed`, outside the repo so OneDrive doesn't sync it.
- Each paper is embedded as `"<title>. <abstract>"`. About 20 papers/s on a laptop, so the
  full 50K takes ~40 minutes.
- `embed_papers` skips papers that already have a vector (resume after a crash; `--force` to
  redo). `build_authors` rebuilds every profile each run.
- Both create or update their vector index from `mongo/vector-indexes.json` and wait until
  it's queryable.
- Point them at A's real file with `--content` / `--meta`.
