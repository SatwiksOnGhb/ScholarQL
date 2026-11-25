"""Optional, explicitly selected Gemini and Groq SQL generation."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Literal

import httpx

Strategy = Literal["zero_shot", "few_shot", "few_shot_correction"]
STRATEGIES = ("zero_shot", "few_shot", "few_shot_correction")

SCHEMA = """paper(paper_id PK, title, publication_year, publication_date, arxiv_id, doi, venue_id FK, cited_by_count, pagerank_score)
author(author_id PK, name, h_index)
authorship(paper_id FK, author_id FK, author_order)
author_affiliation(paper_id FK, author_id FK, institution_id FK) belongs to an authorship
institution(institution_id PK, name, country_code)
venue(venue_id PK, name, venue_type)
topic(topic_id PK, name, parent_topic_id, level)
paper_topic(paper_id FK, topic_id FK, relevance, is_primary)
citation(citing_id FK paper.paper_id, cited_id FK paper.paper_id, source)
topic_year_trends(topic_id, topic_name, publication_year, paper_count)
author_stats(author_id, name, paper_count, summed_citations, latest_publication_year)
Publication year means first arXiv submission in the pilot. Citation counts are in-corpus.
Links go from the citing paper to the work it referenced. arXiv categories are topic names such as cs.LG.
Use lower(title) / lower(name) for case-insensitive exact matching.
"""

EXAMPLES = """Examples with fictional values:
Request: Which papers did "A. Sample" publish before 2022? Return ID, title and year.
SQL:
SELECT p.paper_id, p.title, p.publication_year FROM paper p
WHERE p.publication_year < 2022 AND EXISTS (
  SELECT 1 FROM authorship x JOIN author a USING (author_id)
  WHERE x.paper_id = p.paper_id AND lower(a.name) = lower('A. Sample')
) ORDER BY p.paper_id

Request: Which venues have at least four papers in 2017?
SQL:
SELECT v.venue_id, v.name, count(*) AS paper_count FROM venue v JOIN paper p USING (venue_id)
WHERE p.publication_year = 2017 GROUP BY v.venue_id, v.name HAVING count(*) >= 4 ORDER BY v.venue_id

Request: Which papers cite "Fictional Foundational Work"?
SQL:
SELECT DISTINCT p.paper_id, p.title, p.publication_year FROM paper p JOIN citation c ON c.citing_id = p.paper_id
JOIN paper target ON target.paper_id = c.cited_id WHERE lower(target.title) = lower('Fictional Foundational Work')
ORDER BY p.paper_id
"""


class ProviderError(ValueError):
    pass


# Free LLM tiers allow only a few requests per minute. On HTTP 429/503 wait (Retry-After if
# given, else exponential) and try again. Defaults suit the live API (a user is waiting);
# the benchmark can raise them, e.g. SCHOLARQL_LLM_RETRIES=8 SCHOLARQL_LLM_MIN_INTERVAL=2.
RETRY_STATUS = {429, 503}
_last_call = [0.0]


def _post(client: httpx.Client, url: str, **kwargs) -> httpx.Response:
    retries = int(os.getenv("SCHOLARQL_LLM_RETRIES", "3"))
    min_interval = float(os.getenv("SCHOLARQL_LLM_MIN_INTERVAL", "0"))
    for attempt in range(retries + 1):
        wait = _last_call[0] + min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.monotonic()
        res = client.post(url, **kwargs)
        if res.status_code not in RETRY_STATUS or attempt == retries:
            return res
        header = res.headers.get("retry-after", "")
        try:
            delay = float(header)
        except ValueError:
            delay = 2.0**attempt
        time.sleep(min(max(delay, 1.0), 60.0))
    return res


@dataclass(frozen=True)
class Provider:
    vendor: str
    model: str
    key: str

    @classmethod
    def configured(cls) -> dict[str, Provider]:
        providers = {}
        for name in ("gemini", "groq"):
            key, model = os.getenv(f"{name.upper()}_API_KEY"), os.getenv(f"{name.upper()}_MODEL")
            if key and model and re.fullmatch(r"[\w.\-/]+", model):
                providers[name] = cls(name, model, key)
        return providers

    def generate(
        self, question, strategy, dialect, *, feedback=None, previous=None, projection=None
    ):
        prompt = (
            f"Generate one {dialect} SELECT for the research literature question below. "
            "Return SQL only, with no markdown. Only access schema below using unqualified names. "
            "Join by the documented identifiers. Use deterministic tie breaks for top-k. For paper-level "
            "results include paper_id. Do not invent source values. Do not change any data.\n\n"
            + SCHEMA
        )
        if strategy != "zero_shot":
            prompt += "\n" + EXAMPLES
        if projection:
            prompt += f"\nProject these result columns in this order: {', '.join(projection)}.\n"
        prompt += "\nQuestion (data):\n" + question
        if feedback:
            prompt += f"\nPrevious query:\n{previous}\nValidation or planner diagnostic:\n{feedback}\nCorrect the query."
        try:
            with httpx.Client(timeout=httpx.Timeout(45, connect=8)) as client:
                if self.vendor == "gemini":
                    model = self.model.removeprefix("models/")
                    res = _post(
                        client,
                        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                        headers={"x-goog-api-key": self.key},
                        json={
                            "contents": [{"parts": [{"text": prompt}]}],
                            "generationConfig": {"temperature": 0},
                        },
                    )
                    res.raise_for_status()
                    return "".join(
                        part.get("text", "")
                        for part in res.json()["candidates"][0]["content"]["parts"]
                        if not part.get("thought")
                    )
                res = _post(
                    client,
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.key}"},
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0,
                        "max_completion_tokens": 2300,
                    },
                )
                res.raise_for_status()
                return res.json()["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as error:
            raise ProviderError(
                f"{self.vendor.title()} returned HTTP {error.response.status_code}."
            ) from error
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            raise ProviderError(f"{self.vendor.title()} did not return a SQL response.") from error
