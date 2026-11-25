"""Build the C-owned papers_content.jsonl contract from OpenAlex JSONL."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def abstract_from_index(index: dict[str, list[int]] | None) -> str | None:
    if not index:
        return None
    positions = [position for values in index.values() for position in values]
    if not positions:
        return None
    tokens: list[str | None] = [None] * (max(positions) + 1)
    for word, positions in index.items():
        for position in positions:
            tokens[position] = word
    return " ".join(token for token in tokens if token is not None)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, default=Path("data/papers_content.jsonl"))
    parser.add_argument("--semantic-scholar", type=Path)
    args = parser.parse_args()
    enrichment: dict[str, dict[str, Any]] = {}
    if args.semantic_scholar:
        for line in args.semantic_scholar.open(encoding="utf-8"):
            item = json.loads(line)
            if item.get("openalex_id"):
                enrichment[item["openalex_id"]] = item
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_suffix(args.out.suffix + ".tmp")
    count = 0
    with (
        args.input.open(encoding="utf-8") as source,
        tmp.open("w", encoding="utf-8", newline="\n") as output,
    ):
        for line in source:
            work: dict[str, Any] = json.loads(line)
            openalex_id = work.get("id")
            if not openalex_id:
                continue
            paper_id = openalex_id.removeprefix("https://openalex.org/")
            arxiv_id = (work.get("ids") or {}).get("arxiv")
            if arxiv_id:
                arxiv_id = arxiv_id.removeprefix("https://arxiv.org/abs/").removeprefix(
                    "http://arxiv.org/abs/"
                )
            else:
                doi = (work.get("doi") or "").lower()
                arxiv_id = doi.split("10.48550/arxiv.", 1)[1] if "10.48550/arxiv." in doi else None
            if arxiv_id:
                arxiv_id = re.sub(r"v\d+$", "", arxiv_id)
            content = {
                "paper_id": paper_id,
                "abstract": work.get("abstract")
                or enrichment.get(openalex_id, {}).get("abstract")
                or abstract_from_index(work.get("abstract_inverted_index")),
                "title": work.get("title"),
                "publication_year": work.get("publication_year"),
                "doi": work.get("doi"),
                "arxiv_id": arxiv_id,
                "categories": [
                    category
                    for category in (work.get("scholarql_arxiv", {}).get("categories") or "").split(
                        "|"
                    )
                    if category
                ],
                "sources": {
                    "openalex": openalex_id,
                    "arxiv": f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else None,
                    "doi": work.get("doi"),
                },
                "semantic_scholar_paper_id": enrichment.get(openalex_id, {}).get(
                    "semantic_scholar_paper_id"
                ),
                "tldr": enrichment.get(openalex_id, {}).get("tldr"),
            }
            output.write(json.dumps(content, ensure_ascii=False) + "\n")
            count += 1
    tmp.replace(args.out)
    print(f"Wrote {count} content documents to {args.out}")


if __name__ == "__main__":
    main()
