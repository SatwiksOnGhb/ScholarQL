"""Deterministic query intents and hard metadata constraints."""

from __future__ import annotations

import re
from dataclasses import dataclass

NAME = r'"([^"]+)"'
YEAR = r"((?:19|20)\d{2})"
ID = r"(\d{4}\.\d{4,5})"
N = r"([1-9]\d?)"


def normalized(question: str) -> str:
    return question.strip().translate(str.maketrans({"“": '"', "”": '"'})).rstrip("?.! ").strip()


def literal(value: str) -> str:
    # Backslash escaping is disabled in standard PostgreSQL strings.
    # Use standard quoted literals and keep model-generated queries out of this helper.
    return "'" + value.replace("'", "''") + "'"


def exact(column: str, value: str) -> str:
    return f"lower({column}) = lower({literal(value)})"


def sub(pattern: str, question: str):
    match = re.fullmatch(pattern, question, flags=re.I)
    return match.groups() if match else None


def date_clause(relation: str | None, year: str | None) -> str:
    operators = {"in": "=", "since": ">=", "after": ">", "before": "<", "through": "<="}
    return (
        f" AND p.publication_year {operators[relation.lower()]} {int(year)}"
        if relation and year
        else ""
    )


def paper_list(where: str) -> str:
    return f"""
SELECT p.paper_id, p.title, p.publication_year
FROM paper p
WHERE {where}
ORDER BY p.paper_id
""".strip()


def compile_lookup(q: str) -> str | None:
    match = sub(rf"find arxiv paper {ID}", q)
    title = sub(rf"find paper {NAME}", q)
    if match or title:
        where = f"arxiv_id = {literal(match[0])}" if match else exact("title", title[0])
        return f"SELECT paper_id, title, publication_year, arxiv_id FROM paper WHERE {where} ORDER BY paper_id"
    match = sub(rf"list papers published in {YEAR}", q)
    if match:
        return paper_list("p.publication_year = " + str(int(match[0])))
    match = sub(rf"list papers between {YEAR} and {YEAR}", q)
    if match:
        return paper_list(f"p.publication_year BETWEEN {int(match[0])} AND {int(match[1])}")
    match = sub(rf"find papers with {NAME} in the title", q)
    if match:
        return paper_list(f"strpos(lower(p.title), lower({literal(match[0])})) > 0")
    match = sub(rf"show the {N} most cited papers from {YEAR}", q)
    if match:
        return f"""
SELECT paper_id, title, cited_by_count FROM paper
WHERE publication_year = {int(match[1])}
ORDER BY cited_by_count DESC, paper_id LIMIT {int(match[0])}
""".strip()
    return None


def compile_joins(q: str) -> str | None:
    date = rf"(?: (in|since|after|before|through) {YEAR})?"
    match = sub(rf"(?:list )?papers by {NAME}{date}", q)
    if match:
        return paper_list(f"""
EXISTS (SELECT 1 FROM authorship au JOIN author a USING (author_id)
        WHERE au.paper_id = p.paper_id AND {exact("a.name", match[0])}){date_clause(*match[1:])}""")
    match = sub(rf"(?:list )?papers tagged {NAME}{date}", q)
    if match:
        return paper_list(f"""
EXISTS (SELECT 1 FROM paper_topic pt JOIN topic t USING (topic_id)
        WHERE pt.paper_id = p.paper_id AND {exact("t.name", match[0])}){date_clause(*match[1:])}""")
    match = sub(rf"(?:list )?papers at {NAME}{date}", q)
    if match:
        return paper_list(f"""
EXISTS (SELECT 1 FROM venue v WHERE v.venue_id = p.venue_id
        AND {exact("v.name", match[0])}){date_clause(*match[1:])}""")
    match = sub(rf"(?:list )?authors of {NAME}", q)
    if match:
        return f"""
SELECT a.author_id, a.name FROM author a
JOIN authorship au USING (author_id) JOIN paper p USING (paper_id)
WHERE {exact("p.title", match[0])} ORDER BY p.paper_id, au.author_order
""".strip()
    match = sub(rf"(?:list )?authors affiliated with {NAME}{date}", q)
    if match:
        return f"""
SELECT DISTINCT a.author_id, a.name FROM author a
JOIN author_affiliation aa USING (author_id) JOIN institution i USING (institution_id)
JOIN paper p USING (paper_id) WHERE {exact("i.name", match[0])}{date_clause(*match[1:])}
ORDER BY a.author_id
""".strip()
    match = sub(rf"(?:list )?coauthors of {NAME}", q)
    if match:
        return f"""
SELECT DISTINCT a.author_id, a.name FROM author a
JOIN authorship co ON co.author_id = a.author_id
JOIN authorship seed ON seed.paper_id = co.paper_id AND seed.author_id <> co.author_id
JOIN author source ON source.author_id = seed.author_id
WHERE {exact("source.name", match[0])} ORDER BY a.author_id
""".strip()
    return None


def compile_aggregation(q: str) -> str | None:
    match = sub(rf"count papers(?: tagged {NAME})? by year", q)
    if match:
        condition = (
            ""
            if not match[0]
            else f"""
AND EXISTS (SELECT 1 FROM topic t JOIN paper_topic pt USING (topic_id)
            WHERE pt.paper_id = p.paper_id AND {exact("t.name", match[0])})"""
        )
        return f"""
SELECT p.publication_year, count(*) AS paper_count FROM paper p
WHERE p.publication_year IS NOT NULL {condition}
GROUP BY p.publication_year ORDER BY p.publication_year
""".strip()
    match = sub(rf"count citations received by {NAME}", q)
    if match:
        return f"""
SELECT p.paper_id, count(c.citing_id) AS citation_count
FROM paper p LEFT JOIN citation c ON c.cited_id = p.paper_id
WHERE {exact("p.title", match[0])}
GROUP BY p.paper_id ORDER BY p.paper_id
""".strip()
    match = sub(
        rf"top {N} (authors by paper count|venues by average citations)(?: (since) {YEAR})?", q
    )
    if match:
        limit, subject, relation, year = match
        condition = date_clause(relation, year)
        if subject.lower().startswith("authors"):
            return f"""
SELECT a.author_id, a.name, count(*) AS paper_count
FROM author a JOIN authorship au USING (author_id) JOIN paper p USING (paper_id)
WHERE 1 = 1 {condition}
GROUP BY a.author_id, a.name ORDER BY paper_count DESC, a.author_id LIMIT {int(limit)}
""".strip()
        return f"""
SELECT v.venue_id, v.name, round(cast(avg(p.cited_by_count) AS numeric), 3) AS avg_citations
FROM venue v JOIN paper p USING (venue_id) WHERE 1 = 1 {condition}
GROUP BY v.venue_id, v.name ORDER BY avg_citations DESC, v.venue_id LIMIT {int(limit)}
""".strip()
    match = sub(rf"count distinct authors per venue in {YEAR}", q)
    if match:
        return f"""
SELECT v.venue_id, v.name, count(DISTINCT au.author_id) AS author_count
FROM venue v JOIN paper p USING (venue_id) JOIN authorship au USING (paper_id)
WHERE p.publication_year = {int(match[0])}
GROUP BY v.venue_id, v.name ORDER BY v.venue_id
""".strip()
    match = sub(rf"count papers with at least {N} authors by year", q)
    if match:
        return f"""
SELECT p.publication_year, count(*) AS paper_count FROM paper p
WHERE p.publication_year IS NOT NULL AND
      (SELECT count(*) FROM authorship au WHERE au.paper_id = p.paper_id) >= {int(match[0])}
GROUP BY p.publication_year ORDER BY p.publication_year
""".strip()
    return None


def reachability(where: str, depth: int) -> str:
    return f"""
WITH RECURSIVE walk(paper_id, depth, path) AS (
    SELECT p.paper_id, 0, '|' || p.paper_id || '|' FROM paper p WHERE {where}
    UNION ALL
    SELECT c.cited_id, w.depth + 1, w.path || c.cited_id || '|'
    FROM walk w JOIN citation c ON c.citing_id = w.paper_id
    WHERE w.depth < {min(5, depth)} AND w.path NOT LIKE '%|' || c.cited_id || '|%'
)
SELECT p.paper_id, p.title, min(w.depth) AS depth
FROM walk w JOIN paper p USING (paper_id)
WHERE w.depth > 0 GROUP BY p.paper_id, p.title ORDER BY depth, p.paper_id
""".strip()


def compile_nested(q: str) -> str | None:
    match = sub(rf"(?:show )?(?:the )?citation chain from {NAME} up to depth ([1-5])", q)
    if match:
        return reachability(exact("p.title", match[0]), int(match[1]))
    match = sub(rf"(?:list )?papers that cite (both )?{NAME} (but not|and) {NAME}", q)
    if match:
        _, first, relation, second = match
        clauses = []
        for is_negated, title in [(False, first), (relation.lower() == "but not", second)]:
            clauses.append(f"""{"NOT " if is_negated else ""}EXISTS
  (SELECT 1 FROM citation c JOIN paper target ON target.paper_id = c.cited_id
   WHERE c.citing_id = p.paper_id AND {exact("target.title", title)})""")
        return paper_list(" AND ".join(clauses))
    match = sub(rf"(?:list )?papers with no incoming citations in {YEAR}", q)
    if match:
        return paper_list(f"""p.publication_year = {int(match[0])}
AND NOT EXISTS (SELECT 1 FROM citation c WHERE c.cited_id = p.paper_id)""")
    match = sub(rf"(?:list )?papers above the average citations in {YEAR}", q)
    if match:
        year = int(match[0])
        return paper_list(f"""p.publication_year = {year} AND p.cited_by_count >
    (SELECT avg(cited_by_count) FROM paper WHERE publication_year = {year})""")
    match = sub(rf"(?:list )?papers tagged both {NAME} and {NAME} since {YEAR}", q)
    if match:
        first, second, year = match
        return paper_list(f"""
p.publication_year >= {int(year)}
AND EXISTS (SELECT 1 FROM paper_topic pt JOIN topic t USING (topic_id)
            WHERE pt.paper_id = p.paper_id AND {exact("t.name", first)})
AND EXISTS (SELECT 1 FROM paper_topic pt JOIN topic t USING (topic_id)
            WHERE pt.paper_id = p.paper_id AND {exact("t.name", second)})""")
    match = sub(rf"(?:list )?papers whose authors published in {YEAR} and {YEAR}", q)
    if match:
        first, second = map(int, match)
        return paper_list(f"""
EXISTS (SELECT 1 FROM authorship au WHERE au.paper_id = p.paper_id
AND EXISTS (SELECT 1 FROM authorship x JOIN paper p1 USING (paper_id)
            WHERE x.author_id = au.author_id AND p1.publication_year = {first})
AND EXISTS (SELECT 1 FROM authorship y JOIN paper p2 USING (paper_id)
            WHERE y.author_id = au.author_id AND p2.publication_year = {second}))""")
    return None


def compile_question(question: str) -> str | None:
    q = normalized(question)
    for compiler in (compile_lookup, compile_joins, compile_aggregation, compile_nested):
        sql = compiler(q)
        if sql:
            return sql
    return None


@dataclass(frozen=True)
class Filters:
    conditions: tuple[str, ...]
    labels: tuple[str, ...]
    concept: str

    @property
    def sql(self) -> str:
        where = "\nWHERE " + "\n  AND ".join(self.conditions) if self.conditions else ""
        return """SELECT p.paper_id FROM paper p""" + where + "\nORDER BY p.paper_id"


def extract_filters(question: str) -> Filters:
    remaining = normalized(question)
    conditions: list[str] = []
    labels: list[str] = []

    def substitute(pattern, produce):
        nonlocal remaining

        def add(match):
            condition, label = produce(*match.groups())
            conditions.append(condition)
            labels.append(label)
            return " "

        remaining = re.sub(pattern, add, remaining, flags=re.I)

    substitute(
        rf"\b(?:published )?between {YEAR} and {YEAR}\b",
        lambda a, b: (f"p.publication_year BETWEEN {int(a)} AND {int(b)}", f"{a}–{b}"),
    )
    substitute(
        rf"\b(?:published )?(since|after|before|through|in) {YEAR}\b",
        lambda op, y: (date_clause(op, y).removeprefix(" AND "), f"{op.lower()} {y}"),
    )
    substitute(
        rf"\b(?:at|in venue) {NAME}",
        lambda value: (
            f"""EXISTS (SELECT 1 FROM venue v WHERE v.venue_id = p.venue_id AND {exact("v.name", value)})""",
            f"venue · {value}",
        ),
    )
    substitute(
        rf"\b(?:by author|by) {NAME}",
        lambda value: (
            f"""EXISTS (SELECT 1 FROM authorship au JOIN author a USING (author_id)
                   WHERE au.paper_id = p.paper_id AND {exact("a.name", value)})""",
            f"author · {value}",
        ),
    )
    substitute(
        rf"\b(?:from institution|affiliated with) {NAME}",
        lambda value: (
            f"""EXISTS (SELECT 1 FROM author_affiliation af JOIN institution i USING (institution_id)
                   WHERE af.paper_id = p.paper_id AND {exact("i.name", value)})""",
            f"institution · {value}",
        ),
    )
    substitute(
        rf"\b(?:tagged|in category) {NAME}",
        lambda value: (
            f"""EXISTS (SELECT 1 FROM paper_topic pt JOIN topic t USING (topic_id)
                   WHERE pt.paper_id = p.paper_id AND {exact("t.name", value)})""",
            f"topic · {value}",
        ),
    )
    substitute(
        r"\b(?:with )?at least ([0-9]{1,6}) incoming citations\b",
        lambda value: (f"p.cited_by_count >= {int(value)}", f"{value}+ in-corpus citations"),
    )
    remaining = re.sub(
        r"^(?:find|show|list|recommend|retrieve)\s+(?:(?:me|the|research)\s+)*(?:papers|articles|work)(?:\s+(?:about|on|explaining|discussing|covering|for|related to))?\b\s*",
        "",
        remaining,
        flags=re.I,
    )
    remaining = re.sub(r"\b(?:with|and|that were)\s*$", "", remaining, flags=re.I)
    return Filters(tuple(conditions), tuple(labels), " ".join(remaining.strip(" ,").split()))


def route_question(question: str, filters: Filters, local_sql: str | None) -> str:
    if local_sql:
        return "sql"
    q = normalized(question).lower()
    conceptual = re.search(
        r"^(?:how|what is|what are|explain|describe|summari[sz]e|compare methods|recommend)\b"
        r"|\b(?:papers|articles|work)\s+(?:about|on|explaining|discussing|covering|for|related to)\b",
        q,
    )
    exact_request = re.search(
        r"\b(?:how many|what(?: is|'s) the number|show the top|which authors|citation chain|"
        r"count|average|above the average|median|intersection|cite both)\b",
        q,
    )
    if conceptual and not exact_request:
        return "hybrid" if filters.conditions else "semantic"
    return "sql"


def unresolved_constraints(concept: str) -> bool:
    """Reject common metadata forms that require an explicit supported filter."""
    return bool(
        re.search(
            r"\b(?:published|publication year|accepted at|by author|in venue|from institution|affiliated with|"
            r"tagged|in category|co-authored|incoming citations|citing|that cite|peer-reviewed|"
            r"earlier than|later than|prior to|at the (?:conference|journal)|"
            r"(?:since|before|after|in|through|during) (?:19|20)\d{2})\b",
            concept,
            flags=re.I,
        )
        or re.search(r"\b(?:at|by) [A-Z][\w-]+\b", concept)
    )


def unsupported_filter_logic(question: str) -> bool:
    """Only conjunctions of positive metadata predicates are compiled."""
    return bool(
        re.search(
            r"\b(?:or|except|excluding|not|other than)\s+(?:published\s+)?"
            r"(?:between|since|after|before|through|in|at|by|tagged|from institution|affiliated with|at least)\b",
            normalized(question),
            flags=re.I,
        )
    )
