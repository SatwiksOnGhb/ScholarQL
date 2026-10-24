# db/init (owned by Person A)

Docker mounts this folder into the Postgres container at `/docker-entrypoint-initdb.d`.
Any `*.sql`, `*.sql.gz` or `*.sh` file here runs once, in alphabetical order, the first
time the `pgdata` volume is created, e.g. `001_schema.sql`, `002_seed.sql`, `003_roles.sql`.

To re-run after changing these files: `docker compose down -v && docker compose up --build`
(`-v` deletes the database volumes).
