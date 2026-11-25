# ScholarQL report: Person C chapters (draft)

NoSQL design, system architecture and deployment. Numbers in `[brackets]` are filled in
once the full 50K-paper dataset is loaded.

---

## 1. NoSQL design (MongoDB)

### 1.1 Why a document store alongside PostgreSQL

PostgreSQL holds everything that has fixed structure and is queried relationally: papers,
authors, venues, institutions, topics, authorships and citations. Three kinds of data fit it
poorly:

| Data | Why not PostgreSQL |
|------|--------------------|
| Abstracts and TLDRs | Long free text, read only by ID, never joined or filtered |
| Embeddings (384 floats each) | Need approximate nearest-neighbour search; Atlas Vector Search does this without a separate vector database |
| Query logs | Shape changes as the engine evolves (attempts, error details, feedback); read only through aggregations |

MongoDB stores these. Both databases use the same key for every entity: the OpenAlex short
ID as a string (`"W2741809807"` for a paper, `"A5023651"` for an author). A MongoDB result
therefore joins PostgreSQL directly, with no mapping table. Keys are strings rather than
numbers because some are not OpenAlex numbers at all: topics are arXiv categories (`"cs.LG"`)
and the arXiv venue is `"arxiv"`.

### 1.2 Collections

**`paper_content`**: one document per paper.

```json
{ "_id": "W2741809807", "abstract": "...", "tldr": "...",
  "embedding": [0.012, -0.034, ...], "year": 2021, "venue_id": "S4306420609" }
```

- `_id` is the paper ID, so a lookup by ID uses the default `_id` index.
- `year` and `venue_id` are copied from PostgreSQL. This is deliberate denormalisation:
  vector search can only pre-filter on fields inside the same document, so filtering by year
  or venue *before* ranking needs them here.
- `embedding` is absent until the embedding job has run, so a paper can be loaded first and
  embedded later.

**`author_profiles`**: one document per author.

```json
{ "_id": "A5023651", "name": "...", "institution_id": "I136199984",
  "embedding": [...], "paper_ids": ["W2741809807", "W3091588028"] }
```

- `embedding` is the normalised mean of the author's paper vectors: a "research profile" the
  reviewer finder compares against a submitted abstract.
- `paper_ids` is **embedded** rather than referenced through a join collection. The list is
  small (most authors have a handful of papers in the subset) and is always read together
  with the profile, to explain each suggestion with the author's closest papers.
- `institution_id` is the author's latest affiliation. It is a vector-index filter field, so
  same-institution conflicts are excluded inside the search.

**`query_logs`**: one document per question asked.

```json
{ "question": "...", "sql": "SELECT ...", "route": "sql", "ok": true,
  "latency_ms": 840, "error": null, "attempts": 2, "row_count": 17,
  "feedback": { "correct": true, "comment": null, "created_at": "..." },
  "created_at": "..." }
```

- `feedback` is an **embedded sub-document**. It has a 1:1 relationship with its log and is
  written once, so a separate collection would only add a lookup.
- Extra fields (`attempts`, `row_count`) are allowed beyond the required ones. This is the
  flexible-schema property the course asks for: the log shape can grow without a migration.

### 1.3 Embed or reference: summary

| Relationship | Choice | Reason |
|--------------|--------|--------|
| Paper → its abstract, TLDR, vector | Embed (same document) | 1:1, always read together |
| Paper → year, venue | Copy from PostgreSQL | Needed as vector-search pre-filters |
| Author → paper IDs | Embed array | Small, bounded, read with the profile |
| Author → institution | Reference by ID | Institution details live in PostgreSQL |
| Log → feedback | Embed sub-document | 1:1, written once |
| Paper ↔ author, paper ↔ citation | Not in MongoDB | Many-to-many graphs belong in PostgreSQL |

### 1.4 Schema validation

MongoDB is schemaless by default, so each collection has a `$jsonSchema` validator
(`mongo/init/01-collections.js`) with `validationLevel: strict` and `validationAction: error`.
It enforces:

- IDs are non-empty strings (the same text keys as PostgreSQL);
- `embedding` is exactly 384 doubles;
- `year` is between 1900 and 2100;
- `route` is one of `sql`, `semantic`, `hybrid`;
- `feedback`, when present, has `correct` (bool) and `created_at` (date).

An invalid insert is rejected by the database, not just by application code.

### 1.5 Indexes

| Collection | Index | Type | Used by |
|------------|-------|------|---------|
| `paper_content` | `paper_embedding`: `embedding` (384-d, cosine) + filters `year`, `venue_id` | Vector search | Semantic search, hybrid router |
| `author_profiles` | `author_embedding`: `embedding` (384-d, cosine) + filter `institution_id` | Vector search | Reviewer finder |
| `author_profiles` | `paper_ids` | Multikey | Co-author fallback lookup |
| `query_logs` | `created_at` desc | B-tree | Analytics time window |
| `query_logs` | `route`, `created_at` desc | Compound | Accuracy and latency by route |

The free Atlas tier allows three search indexes. Two are used; the third is reserved for the
NL-to-SQL engine's retrieved few-shot examples.

### 1.6 Vector search

- **Model:** `BAAI/bge-small-en-v1.5` through fastembed (ONNX Runtime, CPU only, 384 dims).
  Each paper is embedded as `"<title>. <abstract>"`; vectors are unit length.
- **Query:** `$vectorSearch` with `numCandidates ≈ 20 × k` (approximate HNSW search), an
  optional pre-filter on year and venue, and `vectorSearchScore` (cosine mapped to 0–1).
- **Contract for the NL-to-SQL engine:** `vector_search(text, k, filters) → [(paper_id, score)]`.
  The hybrid route takes these IDs and filters them in SQL, e.g. "papers about diffusion
  models from Stanford authors after 2021".

### 1.7 Reviewer finder (cross-database)

1. Look up the submitting authors' profiles and institutions in MongoDB.
2. Get each submitting author's co-authors from PostgreSQL with `coauthors(author_id)` (a
   query over `authorship`).
3. Run `$vectorSearch` on `author_profiles` with the abstract's vector, pre-filtering out the
   submitting authors' institutions. Over-fetch by the number of blocked authors, then drop
   submitting authors and co-authors.
4. Explain each suggestion with the author's three papers closest to the abstract
   (cosine similarity in NumPy over their `paper_ids` vectors), with titles from PostgreSQL.

This is the feature that needs both databases in a single request.

### 1.8 Analytics with aggregation pipelines

`GET /admin/stats` runs one pipeline: `$match` on the time window, then a `$facet` with five
sub-pipelines computed in a single pass:

| Facet | Stages | Output |
|-------|--------|--------|
| `overall` | `$group` | Totals, failures, feedback count, accuracy, p50/p95 latency (`$percentile`) |
| `by_route_week` | `$group` by ISO week × route, `$sort` | Accuracy trend per route |
| `latency_by_route` | `$group` by route | p50 / p95 per route |
| `top_questions` | `$group` on lower-cased, trimmed question, `$sort`, `$limit` | Most-asked questions |
| `failure_reasons` | `$match ok=false`, `$group` on the error class (text before `:`) | Why answers failed |

Accuracy counts only answers that received feedback.

---

## 2. System architecture

```
 Browser ── Next.js (Vercel) ── typed client ──► FastAPI (Render)
                                                  │
                     ┌────────────────────────────┼────────────────────────────┐
                     ▼                            ▼                            ▼
             NL-to-SQL engine              vector_search()              query_logs
          (Gemini / Llama, sqlglot)       (Atlas Vector Search)        (aggregations)
                     │                            │
                     ▼                            ▼
              PostgreSQL (Neon)  ◄── same IDs ──► MongoDB (Atlas M0)
```

- **Backend:** FastAPI on Python 3.12, async throughout. PostgreSQL through a psycopg 3
  connection pool; MongoDB through PyMongo's `AsyncMongoClient`. One request can query both
  databases without blocking.
- **API contract:** FastAPI generates an OpenAPI spec from the Pydantic models; the web app's
  TypeScript types are generated from it. CI regenerates both and fails if either is stale,
  so a change to a response shape that the frontend doesn't match fails the build.
- **Errors:** every error has the same body, `{"error": {"code", "message", "details"}}`.
  When a database is down the API returns 503 for the affected feature, and the rest keeps
  working.
- **Rate limits:** 60 requests/min per IP by default, 10/min on `/ask` and `/reviewers`
  (these spend LLM quota or heavy vector search).
- **Frontend:** Next.js App Router with TypeScript, Tailwind and shadcn/ui; TanStack Query
  for caching, loading and error states. Search state lives in the URL, so a search can be
  shared as a link.
- **Offline jobs:** embedding and author-profile builds run outside the API (`jobs/`), so
  the heavy embedding dependencies stay out of the API image.

### 2.1 Endpoints

| Endpoint | Owner | Databases |
|----------|-------|-----------|
| `POST /ask`, `POST /feedback` | B | PostgreSQL (SQL route, read-only role), MongoDB (semantic/hybrid ranking, log) |
| `GET /papers`, `/papers/{id}`, `/papers/{id}/citations`, `/trends` | A | PostgreSQL (+ abstract from MongoDB) |
| `GET /search`, `/search/venues` | C | MongoDB + PostgreSQL (titles) |
| `POST /reviewers`, `GET /reviewers/authors` | C | MongoDB + PostgreSQL (co-authors) |
| `GET /admin/stats` | C | MongoDB |
| `GET /health` | C | Both (ping) |

---

## 3. Development workflow and deployment

### 3.1 Local development

`docker compose up --build` starts four containers on any laptop: PostgreSQL 17,
`mongodb-atlas-local` (MongoDB with the Atlas search engine, so vector search works offline),
the API (auto-reload) and the web app. Every setting has a default, so a fresh clone needs
no `.env`. Database init scripts create the schema and collections on first start.

### 3.2 Continuous integration (GitHub Actions)

Each pull request and push to `main` runs three jobs in parallel:

| Job | Checks |
|-----|--------|
| Python | Ruff lint and format, lockfiles up to date, pytest, OpenAPI spec up to date |
| Web | Generated API types up to date, ESLint, `next build` (includes type checking) |
| Compose + Playwright | Builds and starts the full stack, waits for health checks, then runs end-to-end smoke tests in Chromium: every page renders, and ask, search, reviewer finder and analytics each get an answer from the API |

### 3.3 Production

| Part | Host (free tier) | Notes |
|------|------------------|-------|
| Web | Vercel | Static assets on a CDN |
| API | Render (Docker) | Sleeps after 15 idle minutes, about 1 min to wake |
| PostgreSQL | Neon | Suspends after 5 idle minutes; wakes on the next query |
| MongoDB | Atlas M0 | 512 MB, 3 search indexes; 50K × 384-d vectors ≈ [100] MB |

Secrets (database URLs, API keys) are environment variables on each host, never committed.
CORS allows only the Vercel domain. Step-by-step setup: `docs/deployment.md`.

---

## 4. Results to fill in

- Semantic search latency p50 / p95 over 50K papers: [ ] ms
- Reviewer finder latency p50 / p95: [ ] ms
- Embedding throughput on a laptop CPU: ~20 papers/s (50K in about [40] min)
- MongoDB storage used: `paper_content` [ ] MB, `author_profiles` [ ] MB
- Example reviewer-finder result showing excluded co-authors (screenshot)
