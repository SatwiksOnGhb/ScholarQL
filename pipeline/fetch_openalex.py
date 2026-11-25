"""Fetch OpenAlex work records for an explicit, auditable arXiv ID list.

The arXiv category list is the scope authority. This script does not infer
cs.LG/cs.AI membership from OpenAlex topic labels.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

API = "https://api.openalex.org/works"
SELECT = ",".join(
    [
        "id",
        "doi",
        "title",
        "publication_year",
        "publication_date",
        "authorships",
        "primary_location",
        "locations",
        "primary_topic",
        "topics",
        "referenced_works",
        "ids",
        "cited_by_count",
        "updated_date",
        "abstract_inverted_index",
    ]
)


def reconstruct_abstract(index: dict[str, list[int]] | None) -> str | None:
    if not index:
        return None
    positions = [position for token_positions in index.values() for position in token_positions]
    if not positions:
        return None
    words: list[str | None] = [None] * (max(positions) + 1)
    for word, token_positions in index.items():
        for position in token_positions:
            words[position] = word
    return " ".join(word for word in words if word is not None)


def read_arxiv_ids(path: Path, limit: int | None = None) -> list[str]:
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames or "arxiv_id" not in reader.fieldnames:
            raise ValueError("manifest CSV must include an arxiv_id column")
        rows = [row for row in reader if row.get("arxiv_id", "").strip()]
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be a positive integer")
        groups: dict[tuple[str, str], list[str]] = {}
        for row in rows:
            identifier = row["arxiv_id"].strip()
            year = (row.get("first_submission_date") or "unknown")[:4]
            categories = set((row.get("categories") or "").split("|")) & {"cs.LG", "cs.AI"}
            primary = row.get("primary_category") or ""
            category = (
                primary
                if primary in categories
                else sorted(categories)[0]
                if categories
                else "unknown"
            )
            groups.setdefault((year, category), []).append(identifier)
        for values_in_group in groups.values():
            values_in_group.sort(key=lambda value: hashlib.sha256(value.encode()).hexdigest())
        values = []
        ordered_groups = sorted(groups)
        round_index = 0
        while len(values) < min(limit, len(rows)):
            found = False
            for group in ordered_groups:
                group_values = groups[group]
                if round_index < len(group_values):
                    values.append(group_values[round_index])
                    found = True
                    if len(values) == limit:
                        break
            if not found:
                break
            round_index += 1
    else:
        values = [row["arxiv_id"].strip() for row in rows]
    if len(values) != len(set(values)):
        raise ValueError("arXiv ID manifest contains duplicates")
    return values


def deduplicate_works(works: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    parent = list(range(len(works)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    seen: dict[str, int] = {}
    for index, work in enumerate(works):
        doi = (
            (work.get("doi") or "")
            .lower()
            .removeprefix("https://doi.org/")
            .removeprefix("http://doi.org/")
            .strip()
        )
        arxiv = (work.get("ids") or {}).get("arxiv") or ""
        arxiv = arxiv.removeprefix("https://arxiv.org/abs/").removeprefix("http://arxiv.org/abs/")
        arxiv = re.sub(r"v\d+$", "", arxiv)
        for key in (f"doi:{doi}" if doi else "", f"arxiv:{arxiv}" if arxiv else ""):
            if not key:
                continue
            if key in seen:
                union(index, seen[key])
            else:
                seen[key] = index

    groups: dict[int, list[dict[str, Any]]] = {}
    for index, work in enumerate(works):
        groups.setdefault(find(index), []).append(work)

    def quality(work: dict[str, Any]) -> tuple[int, int, str]:
        score = sum(
            bool(work.get(field))
            for field in ("abstract", "authorships", "primary_location", "primary_topic")
        )
        score += min(len(work.get("referenced_works") or []), 1000) + len(work.get("topics") or [])
        score += bool(work.get("doi")) + bool((work.get("ids") or {}).get("arxiv"))
        return score, int(work.get("cited_by_count") or 0), str(work.get("id") or "")

    winners: list[dict[str, Any]] = []
    aliases: dict[str, str] = {}
    for members in groups.values():
        winner = max(members, key=quality)
        canonical_id = winner.get("id")
        if not canonical_id:
            continue
        winners.append(winner)
        for member in members:
            if member.get("id"):
                aliases[member["id"]] = canonical_id
    for work in winners:
        references = {aliases.get(item, item) for item in (work.get("referenced_works") or [])}
        work["referenced_works"] = sorted(references - {work["id"]})
    return winners, len(works) - len(winners)


RETRYABLE = {429, 500, 502, 503, 504}
ATTEMPTS = 8


async def get_with_retry(client: httpx.AsyncClient, params: dict) -> httpx.Response:
    """GET with backoff on rate limits, server errors and timeouts (OpenAlex returns
    occasional 502/504s on long DOI filters)."""
    for attempt in range(ATTEMPTS):
        try:
            response = await client.get(API, params=params)
        except (httpx.TimeoutException, httpx.TransportError) as error:
            if attempt == ATTEMPTS - 1:
                raise
            print(f"  network error ({type(error).__name__}); retrying", flush=True)
        else:
            if response.status_code not in RETRYABLE or attempt == ATTEMPTS - 1:
                response.raise_for_status()
                return response
            retry_after = response.headers.get("Retry-After", "")
            if retry_after.isdigit():
                await asyncio.sleep(float(retry_after))
                continue
            print(f"  HTTP {response.status_code}; retrying", flush=True)
        await asyncio.sleep(min(60, 2**attempt))
    raise RuntimeError("unreachable")


async def fetch_batch(
    client: httpx.AsyncClient, ids: list[str], api_key: str | None
) -> list[dict[str, Any]]:
    """Works for a batch of arXiv IDs. If OpenAlex keeps failing on the whole batch, split
    it in half and try again; a single ID that still fails is skipped and reported."""
    try:
        return await _fetch_batch(client, ids, api_key)
    except (httpx.HTTPStatusError, httpx.TransportError) as error:
        status = getattr(getattr(error, "response", None), "status_code", None)
        if status is not None and status < 500 and status != 429:
            raise  # a real client error (bad key, bad filter): stop
        if len(ids) == 1:
            reason = f"HTTP {status}" if status else type(error).__name__  # no URL: it has the key
            print(f"  skipping arXiv {ids[0]}: OpenAlex kept failing ({reason})", flush=True)
            return []
        half = len(ids) // 2
        print(f"  batch of {len(ids)} keeps failing; splitting it", flush=True)
        return await fetch_batch(client, ids[:half], api_key) + await fetch_batch(
            client, ids[half:], api_key
        )


async def _fetch_batch(
    client: httpx.AsyncClient, ids: list[str], api_key: str | None
) -> list[dict[str, Any]]:
    params: dict[str, str | int] = {
        "filter": "doi:" + "|".join(f"10.48550/arxiv.{value}" for value in ids),
        "per_page": 100,
        "cursor": "*",
        "select": SELECT,
    }
    if api_key:
        params["api_key"] = api_key

    results: list[dict[str, Any]] = []
    while True:
        response = await get_with_retry(client, params)
        payload = response.json()
        results.extend(payload.get("results", []))
        cursor = payload.get("meta", {}).get("next_cursor")
        if (
            not cursor
            or not payload.get("results")
            or len(results) >= payload.get("meta", {}).get("count", len(results))
        ):
            return results
        params["cursor"] = cursor


def matched_arxiv_ids(work: dict, manifest: dict) -> list[str]:
    locations = work.get("locations") or []
    links = [(work.get("ids") or {}).get("arxiv"), work.get("doi")]
    links.extend(
        value
        for location in locations
        for value in (
            location.get("doi"),
            location.get("landing_page_url"),
            location.get("pdf_url"),
        )
    )
    identifiers = set()
    for link in links:
        match = re.search(
            r"(?:arxiv\.|arxiv\.org/(?:abs|pdf)/)(\d{4}\.\d{4,5})(?:v\d+)?(?:\.pdf)?/?$",
            link or "",
            re.I,
        )
        if match and match[1] in manifest:
            identifiers.add(match[1])
    return sorted(identifiers)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arxiv_ids", type=Path, help="CSV manifest from fetch_arxiv_manifest.py")
    parser.add_argument("--out", type=Path, default=Path("data/openalex_works.jsonl"))
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument(
        "--limit",
        type=int,
        help="Deterministic stratified subset size; use 1000 for the seed dataset",
    )
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 100:
        parser.error("--batch-size must be between 1 and 100")

    ids = read_arxiv_ids(args.arxiv_ids, args.limit)
    api_key = os.getenv("OPENALEX_API_KEY")
    if not api_key:
        parser.error("Set OPENALEX_API_KEY for batch collection from the Works list API.")
    selected = set(ids)
    with args.arxiv_ids.open(encoding="utf-8", newline="") as source:
        manifest = {
            row["arxiv_id"].strip(): row
            for row in csv.DictReader(source)
            if row["arxiv_id"].strip() in selected
        }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fetched: dict[str, dict[str, Any]] = {}
    # Checkpoint: every finished batch is appended here, so a rerun resumes where it stopped
    checkpoint = args.out.with_suffix(args.out.suffix + ".partial")
    done_batches: set[int] = set()
    if checkpoint.exists():
        with checkpoint.open(encoding="utf-8") as source:
            for line in source:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    break  # a half-written last line from a crash
                if record.get("batch_done") is not None:
                    done_batches.add(record["batch_done"])
                else:
                    fetched[record["id"]] = record
        print(f"Resuming: {len(done_batches)} batches ({len(fetched)} works) already fetched")
    progress = checkpoint.open("a", encoding="utf-8", newline="\n")
    async with httpx.AsyncClient(
        timeout=60, headers={"User-Agent": "ScholarQL/0.1 (academic DBMS project)"}
    ) as client:
        for start in range(0, len(ids), args.batch_size):
            if start in done_batches:
                continue
            batch = ids[start : start + args.batch_size]
            works = await fetch_batch(client, batch, api_key)
            batch_works = []
            for work in works:
                matches = matched_arxiv_ids(work, manifest)
                if not matches:
                    continue
                scoped = manifest[matches[0]]
                work["scholarql_arxiv"] = dict(scoped, selected_aliases=matches)
                work["ids"] = dict(
                    work.get("ids") or {}, arxiv=f"https://arxiv.org/abs/{matches[0]}"
                )
                if scoped.get("first_submission_date"):
                    work["openalex_publication_year"] = work.get("publication_year")
                    work["publication_year"] = int(scoped["first_submission_date"][:4])
                    work["publication_date"] = scoped["first_submission_date"]
                work["abstract"] = reconstruct_abstract(work.pop("abstract_inverted_index", None))
                fetched[work["id"]] = work
                batch_works.append(work)
            for work in batch_works:
                progress.write(json.dumps(work, ensure_ascii=False) + "\n")
            progress.write(json.dumps({"batch_done": start}) + "\n")
            progress.flush()
            print(
                f"Fetched {min(start + len(batch), len(ids))}/{len(ids)} arXiv IDs; matched {len(fetched)} OpenAlex works"
            )

    progress.close()
    unique_works, duplicate_count = deduplicate_works(list(fetched.values()))
    temp_path = args.out.with_suffix(args.out.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8", newline="\n") as output:
        for work in unique_works:
            output.write(json.dumps(work, ensure_ascii=False) + "\n")
    temp_path.replace(args.out)
    checkpoint.unlink(missing_ok=True)
    coverage = {
        key: work["id"]
        for work in unique_works
        for key in work["scholarql_arxiv"]["selected_aliases"]
    }
    audit = args.out.with_suffix(".audit.csv")
    with audit.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["arxiv_id", "first_submission_date", "categories", "matched_openalex_id"])
        writer.writerows(
            (
                key,
                manifest[key].get("first_submission_date"),
                manifest[key].get("categories"),
                coverage.get(key),
            )
            for key in ids
        )
    print(
        f"Wrote {len(unique_works)} deduplicated works ({duplicate_count} duplicate records removed) to {args.out}"
    )
    print(f"DOI coverage: {len(coverage)}/{len(ids)} selected arXiv IDs; audit at {audit}.")


if __name__ == "__main__":
    asyncio.run(main())
