# ScholarQL

Natural-language query engine over research papers. Ask a question in plain English and
ScholarQL answers it with SQL over PostgreSQL or with semantic search over MongoDB,
showing the generated SQL alongside the answer. DBMS course project, RVCE.

Plan and synopsis: [`docs/`](docs/).

## Quick start

Prerequisite: [Docker Desktop](https://www.docker.com/products/docker-desktop/) (running).

```bash
git clone <repo-url> scholarql
cd scholarql
docker compose up --build
```

The first run downloads images and builds the API and web app (a few minutes). Then:

| Service    | URL / port                                   |
|------------|----------------------------------------------|
| Web app    | http://localhost:3000                        |
| API docs   | http://localhost:8000/docs                   |
| API health | http://localhost:8000/health                 |
| PostgreSQL | `localhost:5432` (user/pass/db: `scholarql`) |
| MongoDB    | `mongodb://scholarql:scholarql@localhost:27017/?directConnection=true` |

No `.env` is needed for local dev. To change ports or passwords, copy `.env.example`
to `.env` and edit it.

On the first start PostgreSQL loads A's schema and B's 353-paper pilot (`db/init`), so Ask
and Papers work at once. For semantic search, the reviewer finder and semantic/hybrid
questions, embed the papers into MongoDB once:

```bash
cd jobs
uv run python -m embed.embed_papers    # pilot abstracts -> paper_content + vector index
uv run python -m embed.build_authors   # author profiles for the reviewer finder
```

If you started the stack before the pilot existed, wipe the old volumes first:
`docker compose down -v` (database init scripts only run on empty volumes).

Useful commands:

```bash
docker compose ps              # status + health of each service
docker compose logs -f api     # follow one service's logs
docker compose down            # stop (data is kept in volumes)
docker compose down -v         # stop AND wipe both databases
```

The API container reloads automatically when you edit files in `api/app/`. For fast web
development, run the web app outside Docker: `cd web && pnpm install && pnpm dev`.

## Deployment

Vercel (web), Render (API), Neon (PostgreSQL) and MongoDB Atlas M0, all free tiers.
Step-by-step guide: [`docs/deployment.md`](docs/deployment.md). Environment variables are
documented in [`.env.example`](.env.example).

## Working without Docker

Start just the databases with `docker compose up postgres mongodb`, then:

- API: `cd api && uv sync && uv run uvicorn app.main:app --reload --loop asyncio:SelectorEventLoop`
  (the `--loop` flag is needed on Windows: psycopg's async mode can't use Windows' default
  event loop; it's harmless elsewhere)
- API tests: `cd api && uv run pytest`
- Web: `cd web && pnpm install && pnpm dev`

## End-to-end tests

Playwright smoke tests (`web/e2e/`) open every page in a real browser and run the ask,
search, reviewer and analytics flows against the running stack. CI runs them after
`docker compose up`. Locally, with the stack running:

```bash
cd web
pnpm exec playwright install chromium   # once
pnpm test:e2e                            # E2E_BASE_URL=https://<vercel-url> to test a deployment
```

## API conventions

- Every error response has the same body: `{"error": {"code", "message", "details"}}`.
  Raise `ApiError(404, "not_found", "...")` from `app/errors.py` in a route.
- Rate limits per IP: 60/min by default, 10/min on `/ask` and `/reviewers`.
- Semantic search for other code (e.g. B's hybrid router), contract 4:
  ```python
  from app.services.vector_search import vector_search

  hits = await vector_search("graph neural networks", k=50, filters={"year_from": 2021})
  # -> [(paper_id, score), ...] best first; filters: year_from, year_to, venue_id
  ```
  Needs embeddings in MongoDB: run the jobs in [`jobs/`](jobs/README.md) first.
- IDs are OpenAlex short IDs as **strings** (`"W2741809807"`, `"A5023651"`, `"S4306420609"`),
  the text primary keys of A's tables and the `_id`s in MongoDB. Topics are arXiv categories
  (`"cs.LG"`), and a few venues aren't OpenAlex IDs (`"arxiv"`), so IDs can't be numbers.
- `POST /ask` calls B's engine through `scholarql.answer.answer(question)` (contract 3,
  `engine/scholarql/answer.py`), in a worker thread. SQL runs as A's read-only
  `scholarql_reader` role; semantic and hybrid questions rank with the MongoDB vectors.
  Every answer and failure is logged with `log_query()`; `POST /feedback` stores the verdict.
- Tests: `cd api && uv run pytest`. Tests that need PostgreSQL with the pilot run when
  `TEST_DATABASE_URL` is set (CI sets it), e.g.
  `TEST_DATABASE_URL=postgresql://scholarql:scholarql@localhost:5432/scholarql`.

## Web conventions

- Call the API only through the typed client in `web/lib/api.ts`:
  `unwrap(api.GET("/papers/{paper_id}", { params: { path: { paper_id: "W2785322465" } } }))`.
  Paths, params and response types are checked at build time.
- **After changing an API model or route**, regenerate the contract files and commit them:
  ```bash
  cd api && uv run python scripts/export_openapi.py   # -> web/lib/openapi.json
  cd ../web && pnpm gen:api                           # -> web/lib/api-types.ts
  ```
  CI fails if either file is stale, and `pnpm build` fails if a page no longer matches the API.
- Shared components live in `web/components/` (shadcn/ui primitives in `components/ui/`;
  add more with `pnpm dlx shadcn@latest add <name>`).

## Repo layout and owners

| Path         | Owner | What                                         |
|--------------|-------|----------------------------------------------|
| `db/`        | A     | Schema (`migrations/`), reader role, index benchmarks; `init/` + `seed/` load it in Docker |
| `pipeline/`  | A (B) | arXiv/OpenAlex harvest, Semantic Scholar enrichment, loader, `papers_content.jsonl` export; `pilot_to_seed.py` |
| `engine/`    | B     | NL-to-SQL engine (`scholarql/`), `answer()` adapter, 100-question benchmark and studies (`data/`, `scripts/`, `results/`, `paper/`) |
| `api/`       | C     | FastAPI app                                  |
| `web/`       | C     | Next.js app shell                            |
| `jobs/embed/`| C     | Embedding job for MongoDB                    |
| `mongo/`     | C     | Collections, validation, vector indexes      |
