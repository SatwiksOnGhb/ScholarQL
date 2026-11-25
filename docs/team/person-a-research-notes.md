# Research notes (checked 25 November 2026)

This summarizes current official documentation relevant to Person A's design. The project PDFs specify an OpenAlex backbone, Semantic Scholar enrichment, PostgreSQL, `pg_trgm`, materialized views, recursive citation queries, and an ingestion window of 2018-2024.

## Data-source implementation notes

- OpenAlex supports works filters and cursor paging. Its current documentation says a free verified API key is needed to follow cursor pages beyond the first page, recommends `per_page=100`, and documents request budgets/rate limits. Keep the key in an environment variable, use bounded retries for 429 responses, log the cursor and batch ID, and resume safely. The OpenAlex key must not be committed.
- OpenAlex work records expose a `primary_topic` hierarchy and other topic metadata. That classification is not the same thing as arXiv's submission categories. The proposed dataset is described as arXiv `cs.LG` and `cs.AI`; therefore exact inclusion must be based on the arXiv category/ID list and retained in the ingest audit data. Do not silently substitute OpenAlex topics for arXiv categories.
- The current OpenAlex implementation retains an `ids.arxiv` filter, but that field is unlisted in the public filter guide. The fetch script uses it to resolve the reviewed arXiv manifest; verify a small sample lookup before a full collection and be prepared to resolve by DOI if that implementation field changes.
- The arXiv Atom API supports category queries, paging, and result IDs; its manual asks clients to leave a three-second gap between successive requests. The included manifest script follows that guidance and stores IDs, first-submission dates, and category tags.
- Semantic Scholar's Academic Graph API supports selected field requests and paper detail/batch endpoints; API keys provide higher rate limits. Enrichment should be best-effort and separately logged so a rate-limit failure does not roll back the OpenAlex core record batch.
- For both APIs, request only the fields used, persist source IDs and timestamps, and treat missing abstracts/venue/affiliations as nullable. A DOI may be missing, so deduplication needs both normalized DOI and arXiv ID, with OpenAlex ID as the stable relational key.

## Database design notes

- PostgreSQL's `pg_trgm` provides trigram similarity operators and GIN/GiST operator classes, suitable for fuzzy author and venue matching. It does not replace exact ID joins.
- PostgreSQL materialized views persist query results and must be refreshed after ingest. The schema uses explicit refresh rather than refreshing inside every row trigger.
- `EXPLAIN ANALYZE` executes the target query and reports actual timings; planner statistics should be updated with `ANALYZE`. Timings depend on dataset, hardware and cache state, so the report must contain measured results, not an assumed performance gain.
- `citation_chain` is bounded to 20 levels and avoids revisiting nodes so cycles or malformed source data cannot recurse forever. In-scope citations are loaded only when both endpoints exist in the selected corpus.

## Sources

- [OpenAlex API authentication, API keys, paging requirements and limits](https://help.openalex.org/api/authentication/)
- [OpenAlex work filters](https://help.openalex.org/api/filtering/)
- [OpenAlex result paging](https://help.openalex.org/api/paging/)
- [OpenAlex API implementation for work filters](https://github.com/ourresearch/openalex-elastic-api/blob/master/works/fields.py)
- [arXiv API User's Manual](https://info.arxiv.org/help/api/user-manual.html)
- [dbmate migration file format](https://github.com/amacneil/dbmate#creating-migrations)
- [Semantic Scholar Academic Graph API reference](https://api.semanticscholar.org/api-docs/)
- [PostgreSQL `pg_trgm`](https://www.postgresql.org/docs/current/pgtrgm.html)
- [PostgreSQL materialized views](https://www.postgresql.org/docs/current/rules-materializedviews.html)
- [PostgreSQL `EXPLAIN`](https://www.postgresql.org/docs/current/sql-explain.html)
