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

- API: `cd api && uv sync && uv run uvicorn app.main:app --reload`
- Web: `cd web && pnpm install && pnpm dev`

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
