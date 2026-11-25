"""Best-effort Semantic Scholar TLDR and citation enrichment by arXiv ID."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

API = "https://api.semanticscholar.org/graph/v1/paper/batch"
FIELDS = (
    "paperId,externalIds,title,abstract,venue,year,tldr,references.paperId,references.externalIds"
)


def arxiv_id(work: dict[str, Any]) -> str | None:
    raw = (work.get("ids") or {}).get("arxiv")
    if raw:
        raw = raw.removeprefix("https://arxiv.org/abs/").removeprefix("http://arxiv.org/abs/")
    else:
        doi = (work.get("doi") or "").lower()
        raw = doi.split("10.48550/arxiv.", 1)[1] if "10.48550/arxiv." in doi else ""
    raw = re.sub(r"v\d+$", "", raw or "")
    return raw or None


def read_works(path: Path) -> list[tuple[str, str]]:
    result = []
    for line in path.open(encoding="utf-8"):
        work = json.loads(line)
        identifier = arxiv_id(work)
        if identifier:
            result.append((work["id"], identifier))
    return result


def post_batch(
    client: httpx.Client, ids: list[str], api_key: str | None
) -> list[dict[str, Any] | None]:
    headers = {"x-api-key": api_key} if api_key else {}
    for attempt in range(6):
        response = client.post(API, params={"fields": FIELDS}, json={"ids": ids}, headers=headers)
        if response.status_code == 429 or response.status_code in (500, 502, 503, 504):
            if attempt == 5:
                response.raise_for_status()
            delay = response.headers.get("Retry-After")
            time.sleep(
                float(delay)
                if delay and delay.replace(".", "", 1).isdigit()
                else min(60, 2**attempt)
            )
            continue
        response.raise_for_status()
        return response.json()
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Deduplicated OpenAlex JSONL")
    parser.add_argument("--out", type=Path, default=Path("data/semantic_scholar_enrichment.jsonl"))
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 100:
        parser.error("--batch-size must be between 1 and 100")
    works = read_works(args.input)
    key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_suffix(args.out.suffix + ".tmp")
    enriched = 0
    with (
        httpx.Client(
            timeout=60, headers={"User-Agent": "ScholarQL/0.1 (academic DBMS project)"}
        ) as client,
        tmp.open("w", encoding="utf-8", newline="\n") as output,
    ):
        for start in range(0, len(works), args.batch_size):
            batch = works[start : start + args.batch_size]
            response = post_batch(client, [f"ARXIV:{arxiv}" for _, arxiv in batch], key)
            for (openalex_id, requested_arxiv), item in zip(batch, response):
                if not item:
                    continue
                external = item.get("externalIds") or {}
                refs = []
                for reference in item.get("references") or []:
                    if reference:
                        refs.append(
                            {
                                "paper_id": reference.get("paperId"),
                                "external_ids": reference.get("externalIds") or {},
                            }
                        )
                record = {
                    "openalex_id": openalex_id,
                    "arxiv_id": external.get("ArXiv") or requested_arxiv,
                    "semantic_scholar_paper_id": item.get("paperId"),
                    "title": item.get("title"),
                    "abstract": item.get("abstract"),
                    "venue": item.get("venue"),
                    "year": item.get("year"),
                    "tldr": (item.get("tldr") or {}).get("text"),
                    "references": refs,
                }
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
                enriched += 1
            print(
                f"Enriched {min(start + len(batch), len(works))}/{len(works)} OpenAlex works; matched {enriched}"
            )
            if start + args.batch_size < len(works):
                time.sleep(1)
    tmp.replace(args.out)
    print(f"Wrote {enriched} Semantic Scholar records to {args.out}")


if __name__ == "__main__":
    main()
