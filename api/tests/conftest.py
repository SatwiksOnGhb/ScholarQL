"""Shared fixtures. Tests marked `needs_postgres` run against a real PostgreSQL with A's schema
and the pilot seed (CI starts one; locally: `docker compose up postgres`, then
TEST_DATABASE_URL=postgresql://scholarql:scholarql@localhost:5432/scholarql uv run pytest).
"""

import os

import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
# A's read-only role, as B's engine uses it in production; defaults to the owner connection
TEST_READER_URL = os.environ.get("TEST_READER_URL") or TEST_DATABASE_URL

needs_postgres = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="set TEST_DATABASE_URL to a database with the pilot seed"
)
