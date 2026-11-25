#!/bin/sh
# A's least-privilege role for B's engine: read-only, statement timeout, SELECT only.
SCHOLARQL_READER_PASSWORD="${SCHOLARQL_READER_PASSWORD:-scholarql_reader}" \
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -f /scholarql-db/roles/reader.sql || exit 1
