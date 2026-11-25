"""Copy the local Docker PostgreSQL (pilot or full corpus) to Neon, then add the reader role.

Copies everything A's schema defines: tables and data, indexes, functions, procedures,
PageRank scores and the materialized views. Then runs db/roles/reader.sql so B's engine can
connect read-only, and prints the SCHOLARQL_DATABASE_URL to paste into Render.

Put these in the repo-root .env (never commit it):
    NEON_DATABASE_URL=postgresql://OWNER:PASSWORD@ep-xxx.REGION.aws.neon.tech/scholarql?sslmode=require
    NEON_READER_PASSWORD=<a strong password you choose for scholarql_reader>

Then, from the repo root with the Docker stack running:
    uv run --project pipeline python db/load_neon.py            # first load (empty Neon)
    uv run --project pipeline python db/load_neon.py --reset    # replace what Neon has

pg_dump and psql run inside the local postgres container, so nothing needs installing.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and not key.strip().startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def reader_url(owner_url: str, password: str) -> str:
    """The same Neon URL with scholarql_reader as the user."""
    parts = urlsplit(owner_url)
    host = parts.netloc.rsplit("@", 1)[-1]
    return urlunsplit(parts._replace(netloc=f"scholarql_reader:{quote(password, safe='')}@{host}"))


def shell(local_tools: bool, script: str, env: dict[str, str]) -> None:
    """Run a shell pipeline inside the postgres container (or locally with --local-tools)."""
    if local_tools:
        cmd = ["sh", "-c", script]
        full_env = {**os.environ, **env}
    else:
        cmd = ["docker", "compose", "exec", "-T"]
        for key, value in env.items():
            cmd += ["-e", f"{key}={value}"]
        cmd += ["postgres", "sh", "-c", script]
        full_env = None
    result = subprocess.run(cmd, cwd=ROOT, env=full_env)
    if result.returncode != 0:
        sys.exit("Failed; see the error above. Nothing else was changed after it.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--reset", action="store_true", help="drop Neon's public schema first")
    parser.add_argument(
        "--source", help="database to copy; default: the Docker one, from POSTGRES_* in .env"
    )
    parser.add_argument("--local-tools", action="store_true", help="use pg_dump/psql on PATH")
    parser.add_argument("--roles-dir", default="/scholarql-db/roles")
    args = parser.parse_args()

    load_env()
    e = os.environ
    user, pw = e.get("POSTGRES_USER", "scholarql"), e.get("POSTGRES_PASSWORD", "scholarql")
    # localhost here is inside the postgres container
    source = (
        args.source
        or f"postgresql://{user}:{pw}@localhost:5432/{e.get('POSTGRES_DB', 'scholarql')}"
    )
    target = os.environ.get("NEON_DATABASE_URL")
    reader_pw = os.environ.get("NEON_READER_PASSWORD")
    if not target or not reader_pw:
        sys.exit(
            "Set NEON_DATABASE_URL and NEON_READER_PASSWORD in .env (see the top of this file)."
        )

    env = {
        "SOURCE_URL": source,
        "TARGET_URL": target,
        "SCHOLARQL_READER_PASSWORD": reader_pw,
        "PGOPTIONS": "-c client_min_messages=warning",
    }
    reset = (
        'psql "$TARGET_URL" -v ON_ERROR_STOP=1 -q '
        '-c "DROP SCHEMA IF EXISTS public CASCADE" -c "CREATE SCHEMA public" && '
        if args.reset
        else ""
    )
    # COMMENT ON EXTENSION needs superuser on Neon, so it's filtered out of the dump
    copy = (
        'pg_dump "$SOURCE_URL" --no-owner --no-privileges '
        "| grep -v '^COMMENT ON EXTENSION' "
        '| psql "$TARGET_URL" -v ON_ERROR_STOP=1 -q -o /dev/null'
    )
    roles = f'psql "$TARGET_URL" -v ON_ERROR_STOP=1 -q -f {shlex.quote(args.roles_dir)}/reader.sql'
    check = (
        'psql "$TARGET_URL" -tA -c "SELECT count(*) || \' papers, \' || '
        "(SELECT count(*) FROM citation) || ' citations' FROM paper\""
    )

    print("Copying the local database to Neon…", flush=True)
    shell(args.local_tools, reset + copy, env)
    print("Creating the read-only role for B's engine…", flush=True)
    shell(args.local_tools, roles, env)
    shell(args.local_tools, check, env)
    print(
        "\nDone. In Render, set\n"
        f"  DATABASE_URL           = (your NEON_DATABASE_URL)\n"
        f"  SCHOLARQL_DATABASE_URL = {reader_url(target, reader_pw)}"
    )


if __name__ == "__main__":
    main()
