# NL-to-SQL benchmark: live LLM results (for B's report chapter)

Run on 2026-11-25 with `engine/scripts/sql_study.py --provider groq`. Raw per-question
results: `engine/results/llm-groq/sql_cases.csv` and `sql_results.json`.

- **Benchmark:** B's 100 questions (`engine/data/sql_benchmark.jsonl`), 25 per tier
  (lookup, joins, aggregation, nested), 80 in canonical wording and 20 paraphrased. Each has
  a gold SQL query.
- **Data:** B's 353-paper real pilot (SQLite) plus a counterfactual copy with shifted years
  and changed citation edges. A question counts as correct ("joint") only if the predicted
  SQL returns the same rows as the gold SQL on **both** snapshots, so it can't pass by
  matching one dataset by chance.
- **LLM:** `openai/gpt-oss-120b` on Groq's free tier, temperature 0, schema-aware prompt.
  Llama models on Groq are now Enterprise-only, which is why GPT-OSS was used. Requests that
  hit rate limits were retried, so all 300 LLM requests returned SQL.

| Generator | Correct (/100) | Lookup | Joins | Aggregation | Nested | Canonical (/80) | Paraphrase (/20) | p95 latency |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| B's rule-based compiler | 80 | 20 | 20 | 20 | 20 | 80 | 0 | 5 ms |
| LLM zero-shot | 83 | 25 | 24 | 21 | 13 | 65 | 18 | 4.6 s |
| LLM few-shot | 83 | 25 | 23 | 20 | 15 | 66 | 17 | 7.0 s |
| LLM few-shot + one self-correction | 84 | 25 | 25 | 20 | 14 | 67 | 17 | 6.7 s |
| **Compiler first, LLM fallback** (estimated from the rows above) | **97–98** | | | | | | | 5 ms when the compiler answers |

## Findings

- The two generators fail in opposite places. The compiler is exact on wording it knows
  (80/80) and abstains on every paraphrase (0/20), and abstaining beats a wrong answer. The
  LLM handles paraphrases (17–18/20) but makes mistakes on standard questions, especially
  nested queries (13–15/25).
- Few-shot examples and one self-correction round barely helped (83 → 84). The single
  repair attempt didn't recover its question.
- **Combining them** (compiler when it parses the question, LLM otherwise) answers 98/100
  zero-shot and 97/100 with few-shot, and known questions stay at millisecond latency. The
  deployed engine now does this (`engine/scholarql/answer.py`, `SCHOLARQL_GENERATOR=auto`).
  The combined score is computed per question from the same run, not from a separate run.
- **Limits:** one LLM, one run, temperature 0, a 353-paper pilot, and a 100-question
  benchmark written by the team. Gemini wasn't run (free-tier daily limits); it can be added
  with `--provider gemini`.

## Corpus used by the deployed app

49,478 papers harvested from OpenAlex (stratified from 234,747 arXiv cs.LG/cs.AI IDs,
2018–2024; 99% matched), loaded into PostgreSQL (Neon). 44,646 have abstracts and are
embedded for semantic search in MongoDB Atlas. The remaining ~4,800 have no abstract in
OpenAlex, so they're available to SQL but not to semantic search.
