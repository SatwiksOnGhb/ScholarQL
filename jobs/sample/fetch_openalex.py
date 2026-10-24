"""Fetch a sample of cs.LG-style papers from OpenAlex, so C's work doesn't wait for A's ingest.

Writes two JSON Lines files (one JSON object per line):

  papers_content.jsonl  {"paper_id", "abstract", "tldr"}
      Exactly the format A's pipeline will hand over (contract 4).
  papers_meta.jsonl     {"paper_id", "title", "year", "doi", "cited_by_count",
                         "venue_id", "venue_name", "authors": [...]}
      Stand-in for what A's PostgreSQL tables will hold. TODO(A): once the database is
      loaded, read these fields from paper/venue/authorship/author/institution instead.

OpenAlex has no arXiv categories, so "cs.LG" is approximated as: on arXiv, tagged with the
"Machine learning" concept, primary topic in the "Artificial Intelligence" subfield,
2018-2024, with an abstract. Most-cited first, so the sample contains well-known papers.

Usage (from jobs/):  uv run python sample/fetch_openalex.py [--n 500] [--out ../data/sample]
Set OPENALEX_API_KEY in the repo-root .env (optional) for a higher daily budget.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

API = "https://api.openalex.org/works"
ARXIV = "S4306400194"
MACHINE_LEARNING = "C119857082"
AI_SUBFIELD = "1702"
FILTER = ",".join(
    [
        f"locations.source.id:{ARXIV}",
        f"concepts.id:{MACHINE_LEARNING}",
        f"primary_topic.subfield.id:{AI_SUBFIELD}",
        "publication_year:2018-2024",
        "has_abstract:true",
    ]
)
FIELDS = ",".join(
    [
        "id",
        "doi",
        "display_name",
        "publication_year",
        "primary_location",
        "authorships",
        "cited_by_count",
        "abstract_inverted_index",
    ]
)
MIN_ABSTRACT_WORDS = 40  # skip stubs like "This paper is withdrawn."
REPO_ROOT = Path(__file__).resolve().parents[2]


def openalex_id(url: str | None) -> int | None:
    """https://openalex.org/W2741809807 -> 2741809807 (the shared numeric ID)."""
    if not url:
        return None
    return int(url.rsplit("/", 1)[-1][1:])


def rebuild_abstract(inverted: dict[str, list[int]] | None) -> str:
    """OpenAlex stores abstracts as {word: [positions]}; put the words back in order."""
    if not inverted:
        return ""
    positions = [(pos, word) for word, poss in inverted.items() for pos in poss]
    return " ".join(word for _, word in sorted(positions))


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, httpx.TransportError)


@retry(
    retry=retry_if_exception(_retryable),
    wait=wait_exponential(min=1, max=30),
    stop=stop_after_attempt(5),
    reraise=True,
)
def fetch_page(client: httpx.Client, page: int) -> dict:
    # Numbered pages work without an API key (cursor paging needs one) and are fine for a
    # sample: OpenAlex serves up to 10,000 results this way.
    params = {
        "filter": FILTER,
        "sort": "cited_by_count:desc",
        "per_page": 200,
        "page": page,
        "select": FIELDS,
    }
    if key := os.environ.get("OPENALEX_API_KEY"):
        params["api_key"] = key
    response = client.get(API, params=params)
    response.raise_for_status()
    return response.json()


def to_records(work: dict) -> tuple[dict, dict] | None:
    abstract = rebuild_abstract(work.get("abstract_inverted_index"))
    if len(abstract.split()) < MIN_ABSTRACT_WORDS:
        return None
    paper_id = openalex_id(work["id"])
    source = (work.get("primary_location") or {}).get("source") or {}

    authors = []
    for order, authorship in enumerate(work.get("authorships") or [], start=1):
        author_id = openalex_id(authorship["author"].get("id"))
        if author_id is None:  # OpenAlex couldn't disambiguate this author; nothing to join on
            continue
        institution = (authorship.get("institutions") or [{}])[0]
        authors.append(
            {
                "author_id": author_id,
                "name": authorship["author"]["display_name"],
                "author_order": order,
                "institution_id": openalex_id(institution.get("id")),
                "institution_name": institution.get("display_name"),
            }
        )

    content = {"paper_id": paper_id, "abstract": abstract, "tldr": None}
    meta = {
        "paper_id": paper_id,
        "title": work["display_name"],
        "year": work["publication_year"],
        "doi": work.get("doi"),
        "cited_by_count": work.get("cited_by_count", 0),
        "venue_id": openalex_id(source.get("id")),
        "venue_name": source.get("display_name"),
        "authors": authors,
    }
    return content, meta


def load_env_file() -> None:
    """Read OPENALEX_API_KEY from the repo-root .env without overriding the real env."""
    env = REPO_ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and not key.strip().startswith("#"):
            os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--n", type=int, default=500, help="number of papers (default 500)")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "data" / "sample")
    args = parser.parse_args()
    load_env_file()

    args.out.mkdir(parents=True, exist_ok=True)
    content_path = args.out / "papers_content.jsonl"
    meta_path = args.out / "papers_meta.jsonl"

    seen: set[int] = set()
    page_no = 1
    with (
        httpx.Client(timeout=30, headers={"User-Agent": "ScholarQL (RVCE DBMS project)"}) as client,
        content_path.open("w", encoding="utf-8", newline="\n") as content_file,
        meta_path.open("w", encoding="utf-8", newline="\n") as meta_file,
    ):
        while len(seen) < args.n:
            page = fetch_page(client, page_no)
            if not page["results"]:
                break  # ran out of matching papers
            for work in page["results"]:
                records = to_records(work)
                if records is None or records[0]["paper_id"] in seen:
                    continue
                content, meta = records
                seen.add(content["paper_id"])
                content_file.write(json.dumps(content, ensure_ascii=False) + "\n")
                meta_file.write(json.dumps(meta, ensure_ascii=False) + "\n")
                if len(seen) >= args.n:
                    break
            page_no += 1
            print(f"  {len(seen)}/{args.n} papers", file=sys.stderr)

    print(f"Wrote {len(seen)} papers to {content_path} and {meta_path}")


if __name__ == "__main__":
    main()
