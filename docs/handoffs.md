# Team hand-offs: status after integrating A's and B's code (2026-11-25)

A (`scholarql.zip`) and B (`ScholarQL_Research.zip`) each built a standalone project. Their
work is now inside this repo, adapted to the shared contracts.

## What came from whom, and where it went

| From | What | Now in |
|------|------|--------|
| A | Schema: 9 tables, indexes, `coauthors()`, `citation_chain()`, PageRank, trend/author views | `db/migrations/` (loaded by `db/init/01-schema.sh`) |
| A | Read-only role `scholarql_reader` | `db/roles/` (`db/init/03-reader.sh`) |
| A | Index benchmark SQL + latency script | `db/bench/` |
| A | Papers / citations / trends API SQL | `api/app/routers/papers.py`, in the shared response shapes |
| A, B | arXiv/OpenAlex pipeline (B's copy is newer: fixed arXiv lookup, keeps arXiv categories) | `pipeline/` |
| B | Engine: routing, local SQL compiler, Gemini/Groq generation with retry, SQL safety, TF-IDF/BM25 | `engine/scholarql/` |
| B | 353-paper real pilot | `db/seed/pilot.sql` + `pilot_content.jsonl` (via `pipeline/pilot_to_seed.py`) |
| B | 100-question SQL benchmark, retrieval labels, studies and results, paper draft | `engine/data/`, `engine/scripts/`, `engine/results/`, `engine/paper/` |

## Mismatches that were fixed on C's side

- **IDs are text** in A's schema (`W…`, `A…`, topics like `cs.LG`, venue `arxiv`), not numbers.
  C's API, MongoDB validator, jobs and web app now use the same strings.
- **Year column** is `publication_year`; C's queries use it.
- **No `answer()`** in B's code: `engine/scholarql/answer.py` wraps B's `SearchEngine` as
  contract 3, uses C's MongoDB vectors for semantic/hybrid ranking (TF-IDF if none yet), and
  leaves logging to the API (B's log shape fails C's validator).
- **No `papers_meta.jsonl`**: C's embedding jobs read titles, years, venues, authors and
  institutions straight from A's tables.
- A's API routes (`/citations/{id}`, `/papers` list shapes) were adapted to the agreed paths.
- B's React app and A's Next.js pages were replaced by real pages in the shared Next.js app
  (Ask workbench, paper library + trends, paper page with citation explorer).

## The remaining items: what's done, and the one step each needs

Everything that could be built or measured without the team's own accounts is done. What's
left needs a free API key or account, so it runs on a teammate's (or C's) own machine.

| Item | Status | To finish |
|------|--------|-----------|
| Full 50K harvest + `papers_content.jsonl` | `pipeline/harvest.py` runs every step in order (manifest, OpenAlex, optional TLDRs, load PostgreSQL, content export, embeddings) and resumes after a failure; the load and export steps were tested on A's schema | Get a free OpenAlex key (https://openalex.org/settings/api), put `OPENALEX_API_KEY=` in `.env`, then `uv run --project pipeline python pipeline/harvest.py --limit 50000 --fresh`. Try `--limit 1000` first. If the arXiv API step stalls, download the arXiv metadata snapshot (Kaggle) and add `--metadata <file>` |
| Load Neon | `db/load_neon.py` copies the local database (pilot or 50K) to Neon and creates the read-only role; tested against a non-superuser owner, as on Neon | Create the Neon project, put `NEON_DATABASE_URL` and `NEON_READER_PASSWORD` in `.env`, run `uv run --project pipeline python db/load_neon.py` |
| Index-benchmark numbers | **Done**: B already ran A's benchmark on 50,000 synthetic papers (40 runs per query, both conditions); results and analysis are now in `docs/team/person-a-report.md` | Optional: re-run on the real harvest with `engine/scripts/index_study.py --dsn ...` |
| LLM keys | B's engine picks them up automatically (`.env` locally, Render in production) | Free keys from Google AI Studio and/or Groq: set `GEMINI_API_KEY` + `GEMINI_MODEL` and/or `GROQ_API_KEY` + `GROQ_MODEL` |
| LLM benchmark scores | B's runner works from the repo (re-run here: rule-based compiler 80/100, same as B's result) | With a key set: `cd engine` then `uv run --project ../api python -m scripts.sql_study --provider gemini --out results/llm` (add `--provider groq` for both). Up to 400 requests per provider. Results land in `engine/results/llm/` |

Before the final demo: `cd jobs && uv run python -m seed.query_logs --clear` removes the fake
analytics logs once real questions are coming in.
