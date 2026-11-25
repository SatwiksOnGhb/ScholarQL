"""Convert the arXiv Atom + OpenAlex DOI pilot cache into a frozen ScholarQL corpus."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"
SCOPE = {"cs.AI", "cs.LG"}
VENUE_TYPES = {"conference", "journal", "book_series", "repository"}
CONFERENCE_NAMES = {
    "acm conference on fairness, accountability, and transparency",
    "international conference on learning representations",
    "international conference on machine learning",
    "neural information processing systems",
    "conference on learning theory",
    "annual meeting of the association for computational linguistics",
    "conference on empirical methods in natural language processing",
    "ieee/cvf conference on computer vision and pattern recognition",
}


def compact(value: str | None) -> str:
    return " ".join((value or "").split())


def short(value: str | None) -> str | None:
    return value.removeprefix("https://openalex.org/") if value else None


def select_venue(record: dict) -> tuple[str, str, str] | None:
    primary = record.get("primary_location") or {}
    locations = [primary, *(record.get("locations") or [])]
    alternatives = []
    for loc in locations:
        s = loc.get("source") or {}
        identifier, name = short(s.get("id")), compact(s.get("display_name"))
        kind = s.get("type", "unknown")
        if not identifier or not name:
            continue
        if name.casefold() in CONFERENCE_NAMES:
            kind = "conference"
        if kind in {"journal", "conference", "book_series"}:
            return identifier, name, kind
        if name.casefold() == "arxiv":
            alternatives.append((identifier, name, "repository"))
    return alternatives[0] if alternatives else None


def arxiv_rows(cache: Path):
    chosen = {}
    for path in sorted(cache.glob("*.xml")):
        if not path.name.startswith(("anchor-", "march-")):
            continue
        for element in ET.parse(path).getroot().findall(ATOM + "entry"):
            link = element.findtext(ATOM + "id")
            arxiv_id = re.sub(r"v\d+$", "", link.rsplit("/", 1)[-1])
            published = element.findtext(ATOM + "published")[:10]
            categories = sorted(
                {category.attrib["term"] for category in element.findall(ATOM + "category")}
            )
            if not "2018" <= published[:4] <= "2024" or not SCOPE.intersection(categories):
                continue
            if arxiv_id in chosen:
                continue
            primary = element.find(ARXIV + "primary_category")
            chosen[arxiv_id] = {
                "arxiv_id": arxiv_id,
                "version_url": link.replace("http://", "https://"),
                "first_submission_date": published,
                "categories": categories,
                "primary": primary.attrib["term"] if primary is not None else categories[0],
                "title": compact(element.findtext(ATOM + "title")),
                "abstract": compact(element.findtext(ATOM + "summary")),
                "arxiv_authors": [
                    compact(author.findtext(ATOM + "name"))
                    for author in element.findall(ATOM + "author")
                ],
                "sample_origin": path.stem,
            }
    return chosen


def openalex_row(cache: Path, identifier: str) -> dict:
    candidate = cache / "alex" / (identifier + ".json")
    if not candidate.exists():
        return {}
    record = json.loads(candidate.read_bytes())
    canonical_doi = f"10.48550/arxiv.{identifier}"
    doi = (record.get("doi") or "").lower()
    links = [(loc.get("landing_page_url") or "").lower() for loc in (record.get("locations") or [])]
    if doi.endswith(canonical_doi) or any(
        re.search(rf"arxiv\.org/(?:abs|pdf)/{re.escape(identifier)}(?:v\d+)?(?:\b|\.pdf)$", link)
        for link in links
    ):
        return record
    return {}


def normalize(cache: Path) -> dict:
    arxiv = arxiv_rows(cache)
    venues = {"arxiv": ["arxiv", "arXiv", "repository"]}
    institutions = {}
    papers = {}
    authors = {}
    topics = {}
    authorships = {}
    affiliations = set()
    paper_topics = []
    documents = []
    references = {}
    aliases = {}
    for identifier, item in sorted(arxiv.items()):
        record = openalex_row(cache, identifier)
        w_id = short(record.get("id"))
        paper_id = w_id or f"arxiv:{identifier}"
        if paper_id in papers:
            aliases[identifier] = papers[paper_id][4]
            continue
        date = item["first_submission_date"]
        venue = select_venue(record)
        venue_id = "arxiv"
        if venue:
            venue_id = "arxiv" if venue[1].casefold() == "arxiv" else venue[0]
            venues[venue_id] = [venue_id, venue[1], venue[2]]
        doi = f"10.48550/arxiv.{identifier}"
        papers[paper_id] = [paper_id, item["title"], int(date[:4]), date, identifier, doi, venue_id]
        for category in item["categories"]:
            topics[category] = [category, category, None, 1]
            paper_topics.append([paper_id, category, None, category == item["primary"]])
        document = {
            "paper_id": paper_id,
            "title": item["title"],
            "abstract": item["abstract"],
            "arxiv_id": identifier,
            "publication_year": int(date[:4]),
            "categories": item["categories"],
            "sample_origin": item["sample_origin"],
            "sources": {"arxiv": item["version_url"], "openalex": record.get("id"), "doi": doi},
        }
        documents.append(document)
        references[paper_id] = record.get("referenced_works") or []
        ordered = record.get("authorships") or [
            {"author": {"display_name": name}} for name in item["arxiv_authors"]
        ]
        for order, source in enumerate(ordered, 1):
            identity = source.get("author") or {}
            name = compact(identity.get("display_name") or source.get("raw_author_name"))
            if not name:
                continue
            author_id = short(identity.get("id"))
            if not author_id or not re.match(r"^A[1-9][0-9]+$", author_id):
                # A paper-specific ID avoids asserting that authors with the same name are identical.
                author_id = (
                    "arxiv-author:"
                    + hashlib.sha256(f"{paper_id}:{order}".encode()).hexdigest()[:18]
                )
            if (paper_id, author_id) in authorships:
                continue
            authors.setdefault(author_id, [author_id, name])
            authorships[paper_id, author_id] = [paper_id, author_id, order]
            for institution in source.get("institutions") or []:
                inst_id, inst_name = (
                    short(institution.get("id")),
                    compact(institution.get("display_name")),
                )
                if inst_id and inst_name:
                    institutions[inst_id] = [inst_id, inst_name, institution.get("country_code")]
                    affiliations.add((paper_id, author_id, inst_id))
    edges = sorted(
        {
            (paper_id, target, "openalex")
            for paper_id, works in references.items()
            for work in works
            if (target := short(work)) in papers and target != paper_id
        }
    )
    entities = {
        "institution": [institutions[key] for key in sorted(institutions)],
        "venue": [venues[key] for key in sorted(venues)],
        "author": [authors[key] for key in sorted(authors)],
        "topic": [topics[key] for key in sorted(topics)],
        "paper": [papers[key] for key in sorted(papers)],
        "authorship": [authorships[key] for key in sorted(authorships)],
        "author_affiliation": sorted(affiliations),
        "paper_topic": sorted(paper_topics),
        "citation": edges,
    }
    return {
        "metadata": {
            "label": "arXiv research pilot",
            "snapshot": "2026-11-25",
            "scope": "First arXiv submission 2018–2024, cs.LG or cs.AI",
            "selection": "First 40 API results for each March cs.LG window, plus a curated anchor ID list screened for scope. Convenience sample.",
            "openalex_matched": sum(bool(x["sources"]["openalex"]) for x in documents),
            "merged_arxiv_aliases": aliases,
            "citation_definition": "Observed OpenAlex references whose two works matched the frozen pilot",
            "year_definition": "First arXiv submission year",
            "sources": [
                "https://info.arxiv.org/help/api/user-manual.html",
                "https://developers.openalex.org/api-reference/works/get-a-single-work",
            ],
        },
        "entities": entities,
        "documents": documents,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache", type=Path)
    parser.add_argument("--out", type=Path, default=Path("data/pilot.json"))
    args = parser.parse_args()
    data = normalize(args.cache)
    args.out.parent.mkdir(exist_ok=True, parents=True)
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with args.out.with_name("pilot_manifest.csv").open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(
            [
                "paper_id",
                "arxiv_id",
                "first_submission_date",
                "categories",
                "sample_origin",
                "arxiv_version_url",
                "openalex_url",
            ]
        )
        dates = {p[0]: p[3] for p in data["entities"]["paper"]}
        for document in data["documents"]:
            writer.writerow(
                [
                    document["paper_id"],
                    document["arxiv_id"],
                    dates[document["paper_id"]],
                    "|".join(document["categories"]),
                    document["sample_origin"],
                    document["sources"]["arxiv"],
                    document["sources"]["openalex"],
                ]
            )
    print(
        {
            **{key: len(value) for key, value in data["entities"].items()},
            "OpenAlex matches": data["metadata"]["openalex_matched"],
        }
    )


if __name__ == "__main__":
    main()
