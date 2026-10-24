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

Useful commands:

```bash
docker compose ps              # status + health of each service
docker compose logs -f api     # follow one service's logs
docker compose down            # stop (data is kept in volumes)
docker compose down -v         # stop AND wipe both databases
```

The API container reloads automatically when you edit files in `api/app/`. For fast web
development, run the web app outside Docker: `cd web && pnpm install && pnpm dev`.

## Working without Docker

Start just the databases with `docker compose up postgres mongodb`, then:

- API: `cd api && uv sync && uv run uvicorn app.main:app --reload --loop asyncio:SelectorEventLoop`
  (the `--loop` flag is needed on Windows: psycopg's async mode can't use Windows' default
  event loop; it's harmless elsewhere)
- API tests: `cd api && uv run pytest`
- Web: `cd web && pnpm install && pnpm dev`

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
- Placeholder routes read `api/app/fake_data.py` (fake IDs). Search for `TODO(A)` and
  `TODO(B)` to find what each teammate swaps in.

## Web conventions

- Call the API only through the typed client in `web/lib/api.ts`:
  `unwrap(api.GET("/papers/{paper_id}", { params: { path: { paper_id: 1001 } } }))`.
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
| `db/`        | A     | PostgreSQL migrations, seed data, functions  |
| `pipeline/`  | A     | OpenAlex + Semantic Scholar ingestion        |
| `engine/`    | B     | NL-to-SQL engine: `answer(question)`         |
| `bench/`     | B     | 100-question benchmark                       |
| `api/`       | C     | FastAPI app                                  |
| `web/`       | C     | Next.js app shell                            |
| `jobs/embed/`| C     | Embedding job for MongoDB                    |
| `mongo/`     | C     | Collections, validation, vector indexes      |
