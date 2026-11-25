# Reproduce the evaluation

Start in the directory containing `run.py`. Install the requirements with your active Python. The saved paper results are in `results/`. Supply a separate output directory for a repeat so the original run is easy to compare.

| Input | Use |
| --- | --- |
| `data/pilot.json` | Frozen metadata, normalized relations and document content |
| `data/pilot_manifest.csv` | Human-readable paper-level provenance |
| `data/sql_benchmark.jsonl` | 100 questions, reference SQL, tiers and ordering flags |
| `data/retrieval_qrels.jsonl` | 24 concept questions and pilot relevance labels |
| `db/bench/scale_fixture.sql` | Synthetic PostgreSQL workload |

## SQL execution

For the quick cross-snapshot check:

```powershell
python -m scripts.sql_study --out rerun/sqlite
```

This builds a second fixture by shifting selected years and changing selected observed edges. It preserves the vocabulary and dimension IDs. Use the alternative fixture for counterfactual evaluation only. The saved PostgreSQL result uses two databases with the same schema. Create each database, bootstrap the pilot in one, export the alternative fixture, then bootstrap the second with that file.

```powershell
python -m scripts.sql_study --export-counterfactual counterfactual.json
# Use the owner DSN for the second database while bootstrapping.
python -m scripts.bootstrap postgres --fixture counterfactual.json
python -m scripts.sql_study --dsn $env:PILOT_READER_URL --counterfactual-dsn $env:ALTERNATE_READER_URL --out rerun/postgres
```

The scorer compares ordered rows for rank/depth/byline questions and bag equality for unordered results. Rows include duplicate values, and column positions matter. SQL aliases can differ. A case counts toward joint execution accuracy only when both outputs match their own gold SQL. Result counts, support, errors, timing and repair metadata are in `sql_cases.csv`.

To run the three prompting strategies for a provider, configure its key and model and append `--provider gemini` or `--provider groq`. The script compares zero-shot, few-shot and few-shot with one correction. It records a correction success only if the repaired query matches gold on both snapshots. An LLM run makes up to 400 requests per provider. Use distinct reported model IDs and include the strategy results, retry counts, latency and failed requests in the paper.

## Document retrieval

```powershell
python -m pip install -r requirements-dense.txt
python -m scripts.download_model
python -m scripts.retrieval_study --dense --out rerun/retrieval
```

The rank cutoff is five by default. The 16 hybrid cases compare BM25 and TF-IDF over eligible rows, against MiniLM on the whole corpus, MiniLM with the first five filtered afterward, and MiniLM ranking the eligible set first. The eight semantic cases have no metadata constraint. Grades are 2 for a direct contribution and 1 for a closely related method or application. Unjudged papers are scored as zero. The labels are a small, single-rater pilot and may miss relevant papers. The paired 95% interval resamples the 16 per-question Recall@5 differences with seed 4801 and 10,000 resamples. Runtime reports each query's median of three warm executions and p95 across those medians.

## PostgreSQL workload

Point the index study at a new database you own. It generates 50,000 synthetic papers, creates and drops secondary index conditions on that database, and preserves the constraint indexes.

```powershell
python -m scripts.index_study --dsn $env:INDEX_LAB_OWNER_URL --out rerun/index
```

The default sequence is baseline, indexed, indexed, baseline. Each block warms each query three times and measures 20 shuffled rounds after the warm-up. Per-query medians and p95 include client execution and fetch on one TCP connection. Each case records a separate `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` plan for both index conditions. The runner compares the returned rows across conditions. Timing depends on cache state, instance settings and the data distribution. Synthetic records should not be used for corpus-quality claims. [PostgreSQL EXPLAIN](https://www.postgresql.org/docs/17/sql-explain.html)

Use `python -m scripts.publish_results` after generating the corresponding JSON files under `results/` to refresh the website's Evaluation page.
