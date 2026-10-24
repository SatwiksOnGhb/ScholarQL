# mongo/ (owned by Person C)

| File | What it does |
|------|--------------|
| `init/01-collections.js` | Creates `paper_content`, `author_profiles`, `query_logs` with `$jsonSchema` validation, plus regular indexes. Runs automatically on the first start of the `mongodb` container. |
| `vector-indexes.json` | Atlas Vector Search index definitions (384-dim cosine). Created by the embedding job (task 7), locally and on Atlas. |

A fourth, **temporary** collection, `sample_paper_meta` (titles, venues, institutions of the
sample papers), is filled by `jobs/embed/embed_papers.py` so the API can show titles before
A's PostgreSQL tables exist. It has no validator and isn't part of contract 4; drop it once
A's data is loaded (TODO(A)).

Atlas M0 allows 3 search indexes in total: `paper_embedding`, `author_embedding`, and one
left for B's examples collection.

## Applying changes

Init scripts only run when the Mongo volume is empty. After editing `01-collections.js`,
re-run it (it's idempotent) instead of wiping data:

```bash
docker compose exec mongodb sh -c 'mongosh "mongodb://$MONGODB_INITDB_ROOT_USERNAME:$MONGODB_INITDB_ROOT_PASSWORD@localhost:27017/?directConnection=true" /docker-entrypoint-initdb.d/01-collections.js'
```

## Gotchas

- IDs must be BSON `int`/`long`. Python ints are fine. In mongosh, numbers above 2^31 become
  doubles and are rejected, so wrap them: `NumberLong("2741809807")`.
- `embedding` must be exactly 384 doubles; documents without it are allowed (not embedded yet).

Against Atlas: `mongosh "<atlas-uri>" mongo/init/01-collections.js` (database `scholarql`,
or set `MONGODB_DB`).
