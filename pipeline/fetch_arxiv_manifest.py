"""Build the cs.LG/cs.AI manifest from versioned arXiv metadata or its legacy API."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import xml.etree.ElementTree as ET
from calendar import monthrange
from datetime import UTC
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx

API = "https://export.arxiv.org/api/query"
ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"
OPEN_SEARCH = "{http://a9.com/-/spec/opensearch/1.1/}"
SCOPE = {"cs.AI", "cs.LG"}


def row(arxiv_id, date, categories, primary, first_year, last_year):
    if (
        not date
        or not arxiv_id
        or not (first_year <= int(date[:4]) <= last_year)
        or not SCOPE.intersection(categories)
    ):
        return None
    return {
        "arxiv_id": re.sub(r"v\d+$", "", arxiv_id.strip()),
        "first_submission_date": date,
        "primary_category": primary,
        "categories": "|".join(sorted(set(categories))),
    }


def from_jsonl(path, first, last):
    with path.open(encoding="utf-8") as source:
        for line in source:
            item = json.loads(line)
            cats = item.get("categories", "").split()
            if not SCOPE.intersection(cats):
                continue
            versions = item.get("versions") or []
            first_version = next(
                (entry for entry in versions if entry.get("version") == "v1"), None
            )
            if not first_version or not first_version.get("created"):
                continue
            date = (
                parsedate_to_datetime(first_version["created"]).astimezone(UTC).date().isoformat()
            )
            result = row(item.get("id"), date, cats, cats[0], first, last)
            if result:
                yield result


async def from_api(first, last):
    async with httpx.AsyncClient(
        timeout=60, headers={"User-Agent": "ScholarQL/1.0 (research corpus)"}
    ) as client:
        requested = False
        for year in range(first, last + 1):
            for month in range(1, 13):
                end = monthrange(year, month)[1]
                query = f"(cat:cs.LG OR cat:cs.AI) AND submittedDate:[{year}{month:02}010000 TO {year}{month:02}{end:02}2359]"
                start = 0
                while True:
                    if requested:
                        await asyncio.sleep(3.2)
                    requested = True
                    response = await client.get(
                        API,
                        params={
                            "search_query": query,
                            "start": start,
                            "max_results": 500,
                            "sortBy": "submittedDate",
                            "sortOrder": "ascending",
                        },
                    )
                    response.raise_for_status()
                    root = ET.fromstring(response.content)
                    entries = root.findall(ATOM + "entry")
                    for entry in entries:
                        primary = entry.find(ARXIV + "primary_category")
                        result = row(
                            entry.findtext(ATOM + "id", "").split("/abs/")[-1],
                            entry.findtext(ATOM + "published", "")[:10],
                            [
                                tag.attrib["term"]
                                for tag in entry.findall(ATOM + "category")
                                if "term" in tag.attrib
                            ],
                            primary.attrib.get("term", "") if primary is not None else "",
                            first,
                            last,
                        )
                        if result:
                            yield result
                    start += len(entries)
                    total = int(root.findtext(OPEN_SEARCH + "totalResults", "0"))
                    print(f"arXiv {year}-{month:02}: {start}/{total}", flush=True)
                    if start >= total:
                        break
                    if not entries:
                        raise ValueError(
                            "ArXiv returned an incomplete window. Use the bulk metadata JSONL."
                        )


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("data/arxiv_manifest.csv"))
    parser.add_argument(
        "--metadata",
        type=Path,
        help="Local decompressed arXiv metadata JSONL from the bulk snapshot.",
    )
    parser.add_argument("--start-year", type=int, default=2018)
    parser.add_argument("--end-year", type=int, default=2024)
    args = parser.parse_args()
    if args.start_year > args.end_year:
        parser.error("--start-year must be <= --end-year")
    if args.metadata:
        rows = {
            item["arxiv_id"]: item
            for item in from_jsonl(args.metadata, args.start_year, args.end_year)
        }
    else:
        rows = {item["arxiv_id"]: item async for item in from_api(args.start_year, args.end_year)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=["arxiv_id", "first_submission_date", "primary_category", "categories"],
        )
        writer.writeheader()
        writer.writerows(rows[key] for key in sorted(rows))
    tmp.replace(args.out)
    print(f"Wrote {len(rows)} arXiv IDs to {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
