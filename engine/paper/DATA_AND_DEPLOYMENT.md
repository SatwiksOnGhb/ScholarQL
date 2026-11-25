# Data and deployment

## Frozen pilot

The pilot combines the first 40 arXiv API hits from each March `cs.LG` query for 2018–2024 with a fixed list of anchor IDs. All retained items have `cs.LG` or `cs.AI` among their arXiv categories and a first arXiv submission date in 2018–2024. Deduplication uses the arXiv ID and the DOI-resolved OpenAlex work ID. The resulting 353 works had OpenAlex matches. The OpenAlex identifier is the canonical join key. The arXiv record supplies the first submission date, title, category and abstract. OpenAlex supplies author IDs, affiliations, venue information and references where available. The citation graph contains 325 observed references after restricting both ends to the pilot. [arXiv API manual](https://info.arxiv.org/help/api/user-manual.html) · [OpenAlex Work endpoint](https://developers.openalex.org/api-reference/works/get-a-single-work)

Venue labels use a journal, conference or book series in the matched OpenAlex locations when available. The arXiv repository is the remaining venue. Author affiliations are per paper and depend on OpenAlex coverage. Queries by venue or affiliation inherit those limits.

`data/pilot_manifest.csv` records the exact arXiv version URL and OpenAlex ID of every item. `data/pilot.json` is the frozen normalized fixture used for experiments. The frozen data preserve the observed source responses as normalized fields. To refresh from APIs, run `python pipeline/fetch_pilot.py` and `python pipeline/normalize_pilot.py raw-research` in a separate checkout. API updates can change the returned records. Reproduce the reported numbers using the included fixture.

arXiv publishes descriptive metadata under CC0. OpenAlex gives the same license for its data. The package contains metadata and abstracts from the API sources and links to the papers. [arXiv API terms](https://info.arxiv.org/help/api/tou.html) · [OpenAlex data license](https://help.openalex.org/hc/en-us/articles/24397285563671-Is-OpenAlex-data-really-free)

## PostgreSQL owner and reader

Create a fresh `scholarql` database and set the owner and reader variables in the environment or a project-root `.env` file. Quote connection strings in PowerShell. If a password contains URI reserved characters, percent-encode them in the connection string. Keep the raw password in `SCHOLARQL_READER_PASSWORD`.

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL owner for migration and ingestion |
| `SCHOLARQL_READER_PASSWORD` | Password used by the bootstrap script to create or update the API reader |
| `SCHOLARQL_DATABASE_URL` | Read-only PostgreSQL connection for the API |
| `SCHOLARQL_CORPUS_LABEL` | Set to `arXiv research pilot` for the supplied corpus |
| `MONGODB_URI` | MongoDB connection for the document store and query log |
| `MONGODB_DATABASE` | Database name, defaults to `scholarql` |
| `SCHOLARQL_LOG_QUERIES` | Set to `0` to disable query logging |
| `SCHOLARQL_CONTENT_PATH` | Optional local JSON or JSONL document file for a configured corpus |

With the environment set, run `python -m scripts.bootstrap both` and `python run.py`. `bootstrap postgres` prepares the relational side alone. The owner needs role creation privileges when supplying the reader password. If using a managed database, have the administrator prepare the reader first. The server uses the separate reader connection.

## Corpus expansion

Use a fresh target database when loading a different corpus. If you have the decompressed arXiv bulk metadata JSONL, this is the fastest way to build the category and date manifest. The CLI can also use the month-paginated Atom API with a 3.2 second request gap. [arXiv bulk data access](https://info.arxiv.org/help/bulk_data/index.html)

```powershell
python pipeline/fetch_arxiv_manifest.py --metadata arxiv-metadata-oai-snapshot.json
python pipeline/fetch_openalex.py data/arxiv_manifest.csv --limit 1000
python -m scripts.bootstrap postgres --schema-only
python pipeline/load_openalex.py data/openalex_works.jsonl
python pipeline/extract_papers_content.py data/openalex_works.jsonl
python -m scripts.bootstrap mongo --fixture data/papers_content.jsonl
```

Set `OPENALEX_API_KEY` for the Works list API and review the generated `openalex_works.audit.csv` before expanding the pilot. `--limit 50000` selects 50,000 arXiv IDs where the manifest is big enough. The final number of loaded papers depends on DOI matches and deduplication. Use the audit to calculate coverage. The loader preserves arXiv categories independently of the OpenAlex taxonomy. For optional enrichment, run `python pipeline/enrich_semantic_scholar.py data/openalex_works.jsonl` and pass its output with `--semantic-scholar` to the relational loader and document extractor. [OpenAlex Work fields and filters](https://developers.openalex.org/api-reference/works) · [Semantic Scholar API](https://api.semanticscholar.org/api-docs/)

For a large corpus, record OpenAlex API coverage, venue and affiliation completeness, document coverage and out-of-corpus citations. Use a new collection or database for a new frozen corpus.

## Atlas Vector Search

The compact MiniLM model has 384 dimensions. Install the dense dependencies, download the pinned model, and run `python -m scripts.bootstrap mongo --dense --atlas-index paper_embeddings` against an Atlas deployment with Vector Search enabled. Wait for the index to become queryable, then set `MONGODB_VECTOR_INDEX=paper_embeddings` and `SCHOLARQL_RETRIEVAL=minilm`. The index defines `embedding` as a cosine vector and `paper_id` as a filter field. The app uses SQL paper IDs as an eligibility filter for the Atlas search. Large eligible sets use exact CPU cosine over the same IDs. The recorded experiments use CPU cosine, and the Atlas index path needs a live deployment to verify. [MongoDB Vector Search documentation](https://www.mongodb.com/docs/vector-search/)

## Gemini and Groq

Set `GEMINI_API_KEY` plus `GEMINI_MODEL`, or `GROQ_API_KEY` plus `GROQ_MODEL`. Use a model ID listed by your provider. Restart the app, open **Query settings**, and select the model. Selecting a cloud model sends the question and schema prompt to that provider. The local compiler and document routes run without those keys. [Gemini generateContent](https://ai.google.dev/api/generate-content) · [Groq API reference](https://console.groq.com/docs/api-reference)
