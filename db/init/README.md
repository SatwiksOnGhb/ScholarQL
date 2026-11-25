# db/init

Docker mounts this folder into the Postgres container at `/docker-entrypoint-initdb.d`
(and the whole `db/` folder at `/scholarql-db`). The scripts run once, in order, the first
time the `pgdata` volume is created:

| Script | Does |
|--------|------|
| `01-schema.sh` | Applies A's migrations in `db/migrations/` (the `migrate:up` half) |
| `02-seed.sh` | Loads `db/seed/pilot.sql`: B's 353 real papers, then PageRank and the trend views. `SCHOLARQL_SEED=none` skips it |
| `03-reader.sh` | Creates A's read-only `scholarql_reader` role (`db/roles/reader.sql`) used by B's engine |

To re-run after changing these files: `docker compose down -v && docker compose up --build`
(`-v` deletes the database volumes).

The same steps against Neon (any PostgreSQL 16+), from the repo root:

```bash
sed -n '/^-- migrate:up/,/^-- migrate:down/p' db/migrations/*.sql | psql "$DATABASE_URL" -v ON_ERROR_STOP=1
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/seed/pilot.sql
SCHOLARQL_READER_PASSWORD=... psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/roles/reader.sql
```

For the full 50K corpus, use A's pipeline (`pipeline/`, see its README) instead of the pilot.
