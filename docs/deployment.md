# Deploying ScholarQL

Four free services, one per part of the stack:

| Part | Host | What it runs |
|------|------|--------------|
| Web app | **Vercel** | Next.js (`web/`) |
| API | **Render** | FastAPI Docker image (`api/Dockerfile`), defined in `render.yaml` |
| PostgreSQL | **Neon** | A's schema and data (empty until A's migrations exist) |
| MongoDB | **Atlas M0** | `paper_content`, `author_profiles`, `query_logs` + 2 vector indexes |

Do the steps in this order: the databases first (the API needs their URLs), then the API
(the web app needs its URL), then the web app (the API's CORS setting needs its URL).
Budget about 45 minutes the first time.

Keep a scratch note of the four values you'll collect: `MONGODB_URI`, `DATABASE_URL`, the
Render URL and the Vercel URL. **Never commit them** or paste them into GitHub.

---

## 1. MongoDB Atlas (M0, free)

1. Sign up at <https://www.mongodb.com/cloud/atlas/register> and create a project `ScholarQL`.
2. **Create a cluster**: choose **M0 (Free)**, provider **AWS**, region **Mumbai (ap-south-1)**,
   name `scholarql`.
3. **Database user**: *Security → Database Access → Add New Database User*. Username
   `scholarql`, a generated password (save it), role *Read and write to any database*.
4. **Network access**: *Security → Network Access → Add IP Address → Allow access from
   anywhere* (`0.0.0.0/0`). Render's free tier has no fixed outgoing IP, so this is required;
   the strong password is what protects the database.
5. **Connection string**: *Clusters → Connect → Drivers → Python*. Copy the
   `mongodb+srv://scholarql:<password>@...` string and put your password in it. This is
   `MONGODB_URI`.

### Create the collections and load the sample data

From the repo root, with the local Docker stack running (`docker compose up`).

In **PowerShell**:

```powershell
$env:MONGODB_URI = "mongodb+srv://scholarql:PASSWORD@scholarql.xxxxx.mongodb.net/?retryWrites=true&w=majority"

# Collections + $jsonSchema validation (uses mongosh inside the local mongodb container)
docker compose exec -e MONGODB_DB=scholarql mongodb mongosh "$env:MONGODB_URI" /docker-entrypoint-initdb.d/01-collections.js

# Embeddings, author profiles, vector indexes, demo analytics (from data/sample/)
cd jobs
uv run python -m embed.embed_papers
uv run python -m embed.build_authors
uv run python -m seed.query_logs
cd ..

Remove-Item Env:MONGODB_URI   # so later local runs use the local database again
```

In Git Bash, use `export MONGODB_URI="..."` / `unset MONGODB_URI` instead, and also
`export MSYS_NO_PATHCONV=1` first: otherwise Git Bash rewrites `/docker-entrypoint-initdb.d/...`
into a Windows path and mongosh can't find the script. No `data/sample/`? Run
`cd jobs && uv run python -m sample.fetch_openalex` first.

Check in Atlas: *Browse Collections* shows the three collections, and *Atlas Search* lists
`paper_embedding` and `author_embedding` as **Active**. M0 allows 3 search indexes; the third
is reserved for B's examples collection.

## 2. Neon (PostgreSQL, free)

1. Sign up at <https://neon.tech> and create a project `scholarql`, region
   **AWS Asia Pacific (Singapore)**, Postgres 17, database name `scholarql`.
2. *Dashboard → Connect*: turn **Connection pooling off** and copy the connection string
   (it ends in `?sslmode=require`). This is `DATABASE_URL`.
   The direct (non-pooled) string is deliberate: psycopg prepares repeated statements, which
   don't mix with the pooler's transaction mode; the API keeps its own small pool anyway.
3. Nothing to load yet. Until A's schema and data are in Neon, the API falls back to
   placeholder data. When A is ready, A runs the migrations in `db/` against this URL.

## 3. Render (API)

1. Sign up at <https://render.com> **with GitHub**, and allow access to the `ScholarQL` repo.
2. *New → Blueprint*, pick the repo. Render reads `render.yaml` and proposes the
   `scholarql-api` service.
3. Fill in the secrets it asks for:
   - `DATABASE_URL`: from step 2
   - `MONGODB_URI`: from step 1
   - `CORS_ORIGINS`: `http://localhost:3000` for now (you'll replace it in step 5)
   - `CORS_ORIGIN_REGEX`: leave empty for now
4. *Apply*. The first build takes 5-10 minutes (it bakes the embedding model into the image).
5. When it's live, open `https://<your-service>.onrender.com/health`. Expect
   `{"status":"ok","postgres":"ok","mongodb":"ok"}`. Note this URL: it's the API URL.

From now on Render redeploys automatically when `main` changes **and CI passes**
(`autoDeployTrigger: checksPass`).

## 4. Vercel (web app)

1. Sign up at <https://vercel.com> **with GitHub**.
2. *Add New → Project*, import the `ScholarQL` repo.
3. **Root Directory**: click *Edit* and choose `web`. Framework preset: Next.js (auto).
4. **Environment Variables** (before the first deploy, because the API URL is baked into
   the browser bundle at build time):
   - `NEXT_PUBLIC_API_URL` = `https://<your-service>.onrender.com` (no trailing slash)
   - `ENABLE_EXPERIMENTAL_COREPACK` = `1` (lets Vercel use pnpm 12 from `web/package.json`)
5. *Deploy*. Note the production URL, e.g. `https://scholarql.vercel.app`.

## 5. Connect them (CORS)

The API only answers browsers from origins it knows. In Render: *scholarql-api →
Environment*:

- `CORS_ORIGINS` = your Vercel production URL, e.g. `https://scholarql.vercel.app`
- optional `CORS_ORIGIN_REGEX` = `https://scholarql(-[a-z0-9-]+)?\.vercel\.app` so Vercel's
  preview deployments (one per branch/PR) work too. Adjust `scholarql` to your project name.

Save; Render restarts the service.

## 6. Check it

Open the Vercel URL:

- [ ] Home page badge says **API ok · PostgreSQL ok · MongoDB ok** (the first visit after a
      quiet spell can take ~1 minute: see "Free-tier behaviour")
- [ ] **Search**: "contrastive learning" returns papers; the year filter narrows them
- [ ] **Reviewers**: "Use an example" → Find reviewers returns names with matching papers
- [ ] **Analytics**: charts show the seeded data
- [ ] **Ask**: returns the placeholder answer; Yes/No saves feedback

Paper titles, venues and institution names come from A's tables in Neon once they exist.
Until then they come from the temporary `sample_paper_meta` collection that `embed_papers`
loads in step 1. If results show titles like "Paper W2963403868", re-run step 1.

---

## Free-tier behaviour (read before a demo)

| Service | Behaviour | What to do |
|---------|-----------|------------|
| Render | Sleeps after 15 min without traffic; the next request takes ~1 min to wake it | Open the site a few minutes before a demo |
| Neon | Suspends compute after 5 min idle; first query ~1 s | Nothing; it wakes on its own |
| Atlas M0 | 512 MB storage, 3 search indexes, shared CPU | Fine for 50K papers × 384-dim vectors (~100 MB) |
| Vercel | Generous; static pages are served from a CDN | Nothing |

## Environment variables

Every variable, with local and production values, is documented in
[`.env.example`](../.env.example). Where each production value lives:

| Variable | Set in | Value |
|----------|--------|-------|
| `DATABASE_URL` | Render | Neon connection string |
| `MONGODB_URI` | Render (and your shell, when loading data into Atlas) | Atlas `mongodb+srv://` string |
| `MONGODB_DB` | `render.yaml` | `scholarql` |
| `CORS_ORIGINS` | Render | Vercel production URL |
| `CORS_ORIGIN_REGEX` | Render (optional) | Vercel preview URL pattern |
| `APP_ENV` | `render.yaml` | `prod` |
| `PORT` | Render (automatic) | 10000 |
| `NEXT_PUBLIC_API_URL` | Vercel | Render URL |
| `ENABLE_EXPERIMENTAL_COREPACK` | Vercel | `1` |
| `GEMINI_API_KEY`, `GROQ_API_KEY` | Render, later (B) | from Google AI Studio / Groq |

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Badge says **API unreachable** | Render asleep or `NEXT_PUBLIC_API_URL` wrong | Wait a minute and reload; check the variable, then *Redeploy* on Vercel (it's baked in at build time) |
| Browser console shows a **CORS** error | `CORS_ORIGINS` doesn't match the exact Vercel URL | Copy the URL from the address bar (https, no trailing slash) into Render |
| `/health` shows `mongodb: down` | Atlas IP access list or password | Check step 1.4; special characters in the password must be URL-encoded |
| `/health` shows `postgres: down` | Wrong Neon string | Use the direct string with `?sslmode=require` |
| Search returns nothing | No embeddings in Atlas | Re-run the jobs in step 1 with `MONGODB_URI` set |
| Vercel build fails on pnpm | Corepack not enabled | Add `ENABLE_EXPERIMENTAL_COREPACK=1` and redeploy |
