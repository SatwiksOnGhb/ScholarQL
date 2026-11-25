#!/bin/sh
# Apply A's dbmate migrations (only the "-- migrate:up" half of each file), in order.
# (The Postgres entrypoint may source this file instead of running it, so no `set -e`.)
for f in /scholarql-db/migrations/*.sql; do
  echo "applying $(basename "$f")"
  sed -n '/^-- migrate:up/,/^-- migrate:down/p' "$f" | grep -v '^-- migrate:down' \
    | psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" || exit 1
done
