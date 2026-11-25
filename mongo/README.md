# mongo/ (owned by Person C)

| File | What it does |
|------|--------------|
| `init/01-collections.js` | Creates `paper_content`, `author_profiles`, `query_logs` with `$jsonSchema` validation, plus regular indexes. Runs automatically on the first start of the `mongodb` container. |
| `vector-indexes.json` | Atlas Vector Search index definitions (384-dim cosine). Created by the embedding job (task 7), locally and on Atlas. |

A fourth, optional collection, `sample_paper_meta` (titles, venues, institutions), is filled
only when the embedding job runs with `--meta <file>` (the OpenAlex sample without
PostgreSQL). The API reads titles from PostgreSQL first and falls back to it. It has no
validator and isn't part of contract 4.

Atlas M0 allows 3 search indexes in total: `paper_embedding`, `author_embedding`, and one
left for B's examples collection.

## Applying changes

Init scripts only run when the Mongo volume is empty. After editing `01-collections.js`,
re-run it (it's idempotent) instead of wiping data:

```bash
docker compose exec mongodb sh -c 'mongosh "mongodb://$MONGODB_INITDB_ROOT_USERNAME:$MONGODB_INITDB_ROOT_PASSWORD@localhost:27017/?directConnection=true" /docker-entrypoint-initdb.d/01-collections.js'
```

## Gotchas

- IDs are strings: the OpenAlex short IDs used as primary keys in PostgreSQL
  (`"W2741809807"`, `"A5023651"`, `"S4306420609"`; a few, like the venue `"arxiv"`, aren't
  OpenAlex IDs at all, which is why they can't be numbers).
- `embedding` must be exactly 384 doubles; documents without it are allowed (not embedded yet).

Against Atlas: `mongosh "<atlas-uri>" mongo/init/01-collections.js` (database `scholarql`,
or set `MONGODB_DB`).
