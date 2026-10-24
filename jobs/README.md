# jobs/ (owned by Person C)

Offline scripts that prepare data. They run on your machine (not in Docker) with their own
uv project, so heavy dependencies like fastembed stay out of the API image.

```bash
cd jobs
uv sync
```

## 1. Sample data (until A's ingest is ready)

```bash
uv run python sample/fetch_openalex.py            # 500 papers -> ../data/sample/
uv run python sample/fetch_openalex.py --n 2000   # more
```

Writes to `data/sample/` (gitignored; re-run to recreate):

- `papers_content.jsonl`: `{"paper_id", "abstract", "tldr"}`, the same format A's pipeline
  will produce. `tldr` is null here (TLDRs come from A's Semantic Scholar step).
- `papers_meta.jsonl`: title, year, venue and authors with institutions; a stand-in for
  A's PostgreSQL tables. `# TODO(A)`: read these from the database once it's loaded.

No API key is needed for a few thousand papers. Beyond 10,000 results OpenAlex requires one:
get a free key at https://openalex.org/settings/api and set `OPENALEX_API_KEY` in `.env`.

## 2. Embeddings and author profiles

Coming in task 7: `embed/embed_papers.py`, `embed/build_authors.py`.
