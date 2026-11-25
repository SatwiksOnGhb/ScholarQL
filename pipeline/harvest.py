"""Build the full corpus end to end: harvest, load PostgreSQL, embed into MongoDB.

Runs A's pipeline steps in order, then C's embedding jobs. Each step's output is kept in data/
(gitignored), and a step whose output already exists is skipped, so after a failure or a
pause just run the same command again.

  1. arXiv manifest      data/arxiv_manifest.csv        (cs.LG / cs.AI IDs, 2018-2024)
  2. OpenAlex works      data/openalex_works.jsonl      (needs OPENALEX_API_KEY in .env)
  3. Semantic Scholar    data/semantic_scholar_enrichment.jsonl   (only with --tldr)
  4. Load PostgreSQL     papers, authors, citations, PageRank, trend views
  5. Content export      data/papers_content.jsonl
  6. Embeddings          MongoDB paper_content + author_profiles (jobs/)

Run from the repo root with the Docker stack up (`docker compose up -d`):

    uv run --project pipeline python pipeline/harvest.py --limit 50000
    uv run --project pipeline python pipeline/harvest.py --limit 1000      # quick trial

--fresh empties both databases first (they otherwise keep B's 353-paper pilot as well).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
load_dotenv(ROOT / ".env")

MANIFEST = DATA / "arxiv_manifest.csv"
WORKS = DATA / "openalex_works.jsonl"
S2 = DATA / "semantic_scholar_enrichment.jsonl"
CONTENT = DATA / "papers_content.jsonl"


def local_database_url() -> str:
    """Owner connection to the Docker PostgreSQL (same defaults as docker-compose.yml)."""
    e = os.environ
    return e.get("DATABASE_URL") or (
        f"postgresql://{e.get('POSTGRES_USER', 'scholarql')}:{e.get('POSTGRES_PASSWORD', 'scholarql')}"
        f"@localhost:{e.get('POSTGRES_PORT', '5432')}/{e.get('POSTGRES_DB', 'scholarql')}"
    )


def run(step: str, cmd: list[str], *, cwd: Path = ROOT, env: dict | None = None) -> None:
    print(f"\n=== {step}\n$ {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, cwd=cwd, env={**os.environ, **(env or {})})
    if result.returncode != 0:
        sys.exit(f"Step failed: {step}. Fix the problem above and run the same command again.")


def python(script: str, *args: str) -> list[str]:
    return [sys.executable, str(ROOT / "pipeline" / script), *args]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--limit", type=int, default=50_000, help="papers to harvest")
    parser.add_argument("--tldr", action="store_true", help="add Semantic Scholar TLDRs (slow)")
    parser.add_argument(
        "--metadata",
        type=Path,
        help="arXiv bulk metadata JSONL (Kaggle snapshot); faster and more complete than the API",
    )
    parser.add_argument("--fresh", action="store_true", help="wipe both databases first")
    parser.add_argument("--skip-embed", action="store_true", help="stop after PostgreSQL")
    args = parser.parse_args()

    if not os.environ.get("OPENALEX_API_KEY") and not WORKS.exists():
        sys.exit("Set OPENALEX_API_KEY in .env first (free: https://openalex.org/settings/api).")
    DATA.mkdir(exist_ok=True)

    if args.fresh:
        # Empty databases: no pilot seed, so the corpus is exactly what this run harvests
        run("Reset databases", ["docker", "compose", "down", "-v"])
        run(
            "Start databases",
            ["docker", "compose", "up", "-d", "--wait", "postgres", "mongodb"],
            env={"SCHOLARQL_SEED": "none"},
        )

    if MANIFEST.exists():
        print(f"=== 1. arXiv manifest: using existing {MANIFEST.name}")
    else:
        extra = ["--metadata", str(args.metadata)] if args.metadata else []
        run("1. arXiv manifest", python("fetch_arxiv_manifest.py", "--out", str(MANIFEST), *extra))

    if WORKS.exists():
        print(f"=== 2. OpenAlex: using existing {WORKS.name} (delete it to harvest again)")
    else:
        run(
            "2. OpenAlex works",
            python(
                "fetch_openalex.py", str(MANIFEST), "--out", str(WORKS), "--limit", str(args.limit)
            ),
        )

    if args.tldr and not S2.exists():
        run(
            "3. Semantic Scholar TLDRs",
            python("enrich_semantic_scholar.py", str(WORKS), "--out", str(S2)),
        )
    s2_args = ["--semantic-scholar", str(S2)] if S2.exists() else []

    db_env = {"DATABASE_URL": local_database_url()}
    run("4. Load PostgreSQL", python("load_openalex.py", str(WORKS), *s2_args), env=db_env)
    run(
        "5. Content export",
        python("extract_papers_content.py", str(WORKS), "--out", str(CONTENT), *s2_args),
    )

    if args.skip_embed:
        return
    jobs = ROOT / "jobs"
    run(
        "6a. Embed papers",
        ["uv", "run", "python", "-m", "embed.embed_papers", "--content", str(CONTENT)],
        cwd=jobs,
        env=db_env,
    )
    run(
        "6b. Author profiles",
        ["uv", "run", "python", "-m", "embed.build_authors"],
        cwd=jobs,
        env=db_env,
    )
    print("\nDone. Next: load the same data into Neon with `python db/load_neon.py`.")


if __name__ == "__main__":
    main()
