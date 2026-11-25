"""Build the frozen 100-case SQL benchmark from independently authored reference queries."""

from __future__ import annotations

import json
from collections import Counter

from scholarql.config import DATA
from scholarql.db import read_pilot

TITLES = (
    "1904.10509",
    "2001.08361",
    "2106.09685",
    "2201.11903",
    "2305.14314",
    "2307.09288",
    "2310.06825",
    "2402.03300",
    "2404.14219",
    "2407.21783",
    "2412.19437",
    "2102.09672",
)


def quote(value):
    return "'" + value.replace("'", "''") + "'"


def papers(where):
    return (
        "SELECT p.paper_id, p.title, p.publication_year FROM paper p WHERE "
        + where
        + " ORDER BY p.paper_id"
    )


def build():
    snapshot = read_pilot()
    entities = snapshot["entities"]
    ids = {p[4]: p for p in entities["paper"]}
    anchors = [ids[identifier] for identifier in TITLES if identifier in ids]
    titles = [p[1] for p in anchors]
    venues = {v[0]: v[1] for v in entities["venue"]}
    affiliations = {i[0]: i[1] for i in entities["institution"]}
    author_names = {a[0]: a[1] for a in entities["author"]}
    people = [
        author_names[aid]
        for _, aid, times in entities["authorship"]
        if _ in {p[0] for p in anchors} and times == 1
    ]
    common_venues = [venues[v] for v, _ in Counter(p[6] for p in entities["paper"]).most_common(5)]
    common_institutions = [
        affiliations[i]
        for i, _ in Counter(x[2] for x in entities["author_affiliation"]).most_common(5)
    ]
    output = []
    serial = Counter()

    def case(tier, form, q, gold, ordered=False, paraphrase=None):
        serial[tier] += 1
        assert '"' not in form
        output.append(
            {
                "id": f"{tier.upper()}-{serial[tier]:02}",
                "tier": tier,
                "form": form,
                "question": paraphrase or q,
                "canonical_question": q,
                "wording": "paraphrase" if paraphrase else "canonical",
                "gold_sql": gold,
                "ordered": ordered,
            }
        )

    for i, row in enumerate(anchors[:5]):
        aid, title = row[4], row[1]
        case(
            "lookup",
            "id",
            f"Find arXiv paper {aid}",
            f"SELECT paper_id,title,publication_year,arxiv_id FROM paper WHERE doi={quote('10.48550/arxiv.' + aid)}",
            paraphrase=f"Return the record for arXiv identifier {aid}." if i == 4 else None,
        )
    for i, title in enumerate(titles[5:10]):
        case(
            "lookup",
            "title",
            f'Find paper "{title}"',
            "SELECT paper_id,title,publication_year,arxiv_id FROM paper WHERE upper(title)=upper("
            + quote(title)
            + ")",
            paraphrase=f'Which record has the exact title "{title}"?' if i == 4 else None,
        )
    for i, year in enumerate(range(2019, 2024)):
        case(
            "lookup",
            "year",
            f"List papers published in {year}",
            papers(f"p.publication_year BETWEEN {year} AND {year}"),
            paraphrase=f"Which records have an arXiv submission year of {year}?"
            if i == 4
            else None,
        )
    for i, (first, last) in enumerate(
        [(2018, 2019), (2019, 2020), (2020, 2021), (2021, 2024), (2022, 2023)]
    ):
        case(
            "lookup",
            "range",
            f"List papers between {first} and {last}",
            papers(f"p.publication_year >= {first} AND p.publication_year <= {last}"),
            paraphrase=f"Return publications spanning {first} through {last}, inclusive."
            if i == 4
            else None,
        )
    for i, word in enumerate(("diffusion", "transformer", "reinforcement", "quantiz", "attention")):
        case(
            "lookup",
            "substring",
            f'Find papers with "{word}" in the title',
            papers(f"lower(p.title) LIKE {quote('%' + word + '%')}"),
            paraphrase=f'Which titles contain "{word}" anywhere?' if i == 4 else None,
        )

    for i, name in enumerate(people[:5]):
        q = f'List papers by "{name}"'
        case(
            "joins",
            "author",
            q,
            papers(
                f"p.paper_id IN (SELECT s.paper_id FROM authorship s WHERE s.author_id IN "
                f"(SELECT author_id FROM author WHERE upper(name)=upper({quote(name)})))"
            ),
            paraphrase=f'Show the papers whose author list contains "{name}".' if i == 4 else None,
        )
    for i, topic in enumerate(("cs.LG", "cs.AI", "cs.CL", "cs.CV", "stat.ML")):
        case(
            "joins",
            "topic",
            f'List papers tagged "{topic}"',
            papers(
                f"p.paper_id IN (SELECT paper_id FROM paper_topic WHERE topic_id={quote(topic)})"
            ),
            paraphrase=f'Which works are classified under "{topic}"?' if i == 4 else None,
        )
    for i, venue in enumerate(common_venues):
        case(
            "joins",
            "venue",
            f'List papers at "{venue}" since 2019',
            papers(
                f"p.publication_year >= 2019 AND p.venue_id IN (SELECT venue_id FROM venue WHERE upper(name)=upper({quote(venue)}))"
            ),
            paraphrase=f'Find records associated with "{venue}" from 2019 onward.'
            if i == 4
            else None,
        )
    for i, (name, year) in enumerate(zip(common_institutions, (2018, 2019, 2020, 2021, 2022))):
        case(
            "joins",
            "affiliation",
            f'List authors affiliated with "{name}" since {year}',
            f"""SELECT a.author_id,a.name FROM author a WHERE a.author_id IN
                 (SELECT aa.author_id FROM author_affiliation aa
                  WHERE aa.institution_id IN (SELECT institution_id FROM institution WHERE upper(name)=upper({quote(name)}))
                  AND aa.paper_id IN (SELECT paper_id FROM paper WHERE publication_year >= {year}))
                 ORDER BY a.author_id""",
            paraphrase=f'Who has a paper dated {year} or later with a "{name}" affiliation?'
            if i == 4
            else None,
        )
    for i, title in enumerate(titles[:5]):
        case(
            "joins",
            "author_order",
            f'List authors of "{title}"',
            f"""SELECT a.author_id,a.name FROM authorship au JOIN author a ON au.author_id=a.author_id
                 WHERE au.paper_id IN (SELECT paper_id FROM paper WHERE upper(title)=upper({quote(title)}))
                 ORDER BY au.paper_id, au.author_order""",
            True,
            paraphrase=f'Give the byline for "{title}" in the listed author order.'
            if i == 4
            else None,
        )

    for i, topic in enumerate(("cs.LG", "cs.AI", "cs.CL", "cs.CV", "stat.ML")):
        case(
            "aggregation",
            "count_topic_year",
            f'Count papers tagged "{topic}" by year',
            f"""SELECT p.publication_year,count(pt.paper_id) AS paper_count FROM paper_topic pt JOIN paper p USING(paper_id)
                 WHERE pt.topic_id={quote(topic)} AND p.publication_year IS NOT NULL
                 GROUP BY p.publication_year ORDER BY p.publication_year""",
            paraphrase=f'For each year, how many articles carry the "{topic}" category?'
            if i == 4
            else None,
        )
    for i, title in enumerate(titles[:5]):
        case(
            "aggregation",
            "count_incoming",
            f'Count citations received by "{title}"',
            f"""SELECT p.paper_id,p.cited_by_count AS citation_count FROM paper p WHERE upper(p.title)=upper({quote(title)})
                 ORDER BY p.paper_id""",
            paraphrase=f'How many in-corpus references point to "{title}"?' if i == 4 else None,
        )
    for i, (limit, year) in enumerate(((3, 2018), (4, 2019), (5, 2020), (7, 2021), (10, 2022))):
        case(
            "aggregation",
            "rank_authors",
            f"Top {limit} authors by paper count since {year}",
            f"""WITH totals AS (SELECT au.author_id,count(*) AS paper_count FROM authorship au
                 WHERE au.paper_id IN (SELECT paper_id FROM paper WHERE publication_year >= {year}) GROUP BY au.author_id)
                 SELECT totals.author_id,a.name,totals.paper_count FROM totals JOIN author a USING(author_id)
                 ORDER BY totals.paper_count DESC,totals.author_id LIMIT {limit}""",
            True,
            paraphrase=f"Rank the {limit} most prolific authors from {year} onward by paper count."
            if i == 4
            else None,
        )
    for i, (limit, year) in enumerate(((3, 2018), (4, 2019), (5, 2020), (7, 2021), (10, 2022))):
        case(
            "aggregation",
            "rank_venues",
            f"Top {limit} venues by average citations since {year}",
            f"""WITH means AS (SELECT venue_id,round(cast(avg(cited_by_count) AS numeric),3) AS avg_citations
                 FROM paper WHERE publication_year >= {year} GROUP BY venue_id)
                 SELECT m.venue_id,v.name,m.avg_citations FROM means m JOIN venue v USING(venue_id)
                 ORDER BY m.avg_citations DESC,m.venue_id LIMIT {limit}""",
            True,
            paraphrase=f"From {year} onward, which {limit} venues have the highest mean incoming citation counts?"
            if i == 4
            else None,
        )
    for i, n in enumerate((2, 3, 4, 5, 6)):
        case(
            "aggregation",
            "author_threshold",
            f"Count papers with at least {n} authors by year",
            f"""SELECT publication_year,count(*) AS paper_count FROM paper
                 WHERE publication_year IS NOT NULL AND paper_id IN
                   (SELECT paper_id FROM authorship GROUP BY paper_id HAVING count(*) >= {n})
                 GROUP BY publication_year ORDER BY publication_year""",
            paraphrase=f"For every year, count papers whose byline has {n} or more authors."
            if i == 4
            else None,
        )

    edge_papers = [p for p in anchors if p[0] in {x[0] for x in entities["citation"]}]
    for i, row in enumerate(edge_papers[-5:]):
        title, depth = row[1], i % 3 + 1
        case(
            "nested",
            "recursive",
            f'Show the citation chain from "{title}" up to depth {depth}',
            f"""WITH RECURSIVE root AS (SELECT paper_id FROM paper WHERE upper(title)=upper({quote(title)})),
                 hops(pid,n) AS (SELECT paper_id,0 FROM root UNION
                 SELECT c.cited_id,h.n+1 FROM hops h JOIN citation c ON h.pid=c.citing_id WHERE h.n < {depth})
                 SELECT p.paper_id,p.title,min(h.n) AS depth FROM paper p JOIN hops h ON h.pid=p.paper_id
                 WHERE h.n>0 AND p.paper_id NOT IN (SELECT paper_id FROM root)
                 GROUP BY p.paper_id,p.title ORDER BY depth,p.paper_id""",
            True,
            paraphrase=f'Which references can I reach from "{title}" within {depth} outgoing citation hops?'
            if i == 4
            else None,
        )
    incoming = Counter(x[1] for x in entities["citation"])
    targets = [p[1] for p in sorted(anchors, key=lambda x: (-incoming[x[0]], x[0]))]
    for i, (a, b) in enumerate(zip(targets, targets[1:6])):

        def citing(title):
            return f"SELECT c.citing_id FROM citation c JOIN paper p ON p.paper_id=c.cited_id WHERE upper(p.title)=upper({quote(title)})"

        case(
            "nested",
            "exclude_citation",
            f'Papers that cite "{a}" but not "{b}"',
            papers(f"p.paper_id IN ({citing(a)} EXCEPT {citing(b)})"),
            paraphrase=f'Find articles referencing "{a}" while excluding articles referencing "{b}".'
            if i == 4
            else None,
        )
    for i, year in enumerate(range(2020, 2025)):
        case(
            "nested",
            "zero_citation",
            f"Papers with no incoming citations in {year}",
            papers(
                f"p.publication_year={year} AND p.paper_id NOT IN (SELECT cited_id FROM citation)"
            ),
            paraphrase=f"Which {year} works are absent from the cited side of every edge?"
            if i == 4
            else None,
        )
    for i, year in enumerate(range(2020, 2025)):
        case(
            "nested",
            "above_year_mean",
            f"Papers above the average citations in {year}",
            f"""WITH counts AS (SELECT p.*,avg(cited_by_count) OVER () AS cohort_mean FROM paper p WHERE publication_year={year})
                 SELECT paper_id,title,publication_year FROM counts WHERE cited_by_count>cohort_mean ORDER BY paper_id""",
            paraphrase=f"List {year} papers whose citation count exceeds the mean for their submission year."
            if i == 4
            else None,
        )
    for i, (a, b, year) in enumerate(
        (
            ("cs.LG", "cs.AI", 2018),
            ("cs.LG", "cs.CL", 2019),
            ("cs.LG", "stat.ML", 2020),
            ("cs.AI", "cs.CL", 2021),
            ("cs.LG", "cs.CV", 2022),
        )
    ):
        case(
            "nested",
            "topic_intersection",
            f'List papers tagged both "{a}" and "{b}" since {year}',
            papers(
                f"p.publication_year>={year} AND p.paper_id IN "
                f"(SELECT paper_id FROM paper_topic WHERE topic_id={quote(a)} INTERSECT "
                f"SELECT paper_id FROM paper_topic WHERE topic_id={quote(b)})"
            ),
            paraphrase=f'Which works from {year} onward belong to the intersection of "{a}" and "{b}"?'
            if i == 4
            else None,
        )

    assert set(serial.values()) == {25}, serial
    (DATA / "sql_benchmark.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in output), encoding="utf-8"
    )


if __name__ == "__main__":
    build()
