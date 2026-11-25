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

## 1. Data

PostgreSQL already holds B's 353-paper pilot after the first `docker compose up` (db/init),
and its abstracts are in `db/seed/pilot_content.jsonl`, so the embedding jobs below work
straight away. For the full corpus, run A's pipeline (`pipeline/`) and pass its
`papers_content.jsonl` with `--content`.

The OpenAlex sample below is optional: a way to get papers without PostgreSQL.

```bash
uv run python -m sample.fetch_openalex            # 500 papers -> ../data/sample/
uv run python -m sample.fetch_openalex --n 2000   # more
```

Writes to `data/sample/` (gitignored; re-run to recreate):

- `papers_content.jsonl`: `{"paper_id", "abstract", "tldr"}`, the same format A's pipeline
  will produce. `tldr` is null here (TLDRs come from A's Semantic Scholar step).
- `papers_meta.jsonl`: title, year, venue and authors with institutions, what A's
  PostgreSQL tables hold. Pass it with `--meta` to run the jobs without PostgreSQL.

No API key is needed for a few thousand papers. Beyond 10,000 results OpenAlex requires one:
get a free key at https://openalex.org/settings/api and set `OPENALEX_API_KEY` in `.env`.

## 2. Embeddings and author profiles

```bash
uv run python -m embed.embed_papers    # pilot papers -> MongoDB paper_content + vector index
uv run python -m embed.build_authors   # author_profiles (mean of their papers) + vector index
```

Titles, years, venues, authors and institutions come from A's PostgreSQL tables.

- Model: `BAAI/bge-small-en-v1.5` via fastembed (384 dims, CPU). Downloaded once (~65 MB) to
  `~/.cache/fastembed`, outside the repo so OneDrive doesn't sync it.
- Each paper is embedded as `"<title>. <abstract>"`. About 20 papers/s on a laptop, so the
  full 50K takes ~40 minutes.
- `embed_papers` skips papers that already have a vector (resume after a crash; `--force` to
  redo). `build_authors` rebuilds every profile each run.
- Both create or update their vector index from `mongo/vector-indexes.json` and wait until
  it's queryable.
- A's full set: `--content ../data/papers_content.jsonl` (from
  `pipeline/extract_papers_content.py`). The sample without PostgreSQL: add
  `--meta ../data/sample/papers_meta.jsonl` to both jobs; `embed_papers` then also fills
  `sample_paper_meta`, which the API reads titles from when PostgreSQL has none.

## 3. Demo analytics data (until B's engine has real traffic)

```bash
uv run python -m seed.query_logs            # 2000 fake query_logs over the last 8 weeks
uv run python -m seed.query_logs --clear    # remove them
```

Fake logs tell a plausible story (usage grows, accuracy improves, realistic failure types)
so the analytics page has something to show. They're tagged `seed: true`; re-running or
`--clear` removes only seeded logs, never real ones. Same `--seed` = same data.
