# ScholarQL
## SQL eligibility before document ranking for research literature queries

### Abstract

Literature search often combines a research concept with exact constraints such as submission year, venue or field. We implement ScholarQL, a browser workbench that routes questions to relational queries, document ranking, or a combination of the two. In the combined route, SQL determines paper eligibility and ranks the linked title and abstract documents within that set. The system reports filter SQL and evidence records for each result. On a frozen pilot of 353 arXiv papers, prefiltering increased MiniLM Recall@5 from 0.583 to 0.750 over filtering after five global hits. The paired absolute gain was 0.167 with a bootstrap 95% interval of 0.068 to 0.276. Among five evaluated methods on the 16 hybrid questions, TF-IDF with prefiltering had the highest recall and BM25 with prefiltering had the highest nDCG@5. A separate 100-question SQL test and controlled 50,000-paper synthetic PostgreSQL workload characterize exact execution and database cost.

### 1. Motivation

Researchers ask questions that mix concept relevance and exact data. For example, to answer “Find papers about adapting language models on a small GPU published since 2023”, the year requirement and the semantic concept must both be evaluated. Global document ranking followed by filtering at the same cutoff can lose relevant eligible items below that cutoff. The experiment asks how applying SQL eligibility before ranking changes retrieval quality, answer coverage and latency on a frozen literature corpus.

Schema-aware text-to-SQL and comparison of denotations across data instances draw on Spider, distilled test suites and DIN-SQL. Our comparison concerns filter placement in a literature workbench, a domain-specific evaluation, and associated evidence traces. [Spider](https://aclanthology.org/D18-1425/) · [Distilled test suites](https://aclanthology.org/2020.emnlp-main.29/) · [DIN-SQL](https://arxiv.org/abs/2304.11015)

### 2. System design

The relational schema stores papers, authors, venues, institutions, topics, authorships, paper-level author affiliations, paper-topic mappings and directed citation edges. MongoDB stores text and optional vectors under the same paper ID and can persist query history. The default portable app reads the frozen pilot through SQLite and a local document snapshot. The full stack uses PostgreSQL and MongoDB.

A rule-based router classifies supported questions as SQL, document search or combined. For combined requests, the filter compiler projects the set of IDs eligible under exact metadata constraints. The ranker computes relevance from each eligible title and abstract. The trace records applied predicates, number of SQL candidates, number with documents and ranking method. For relational requests, the local compiler handles supported query shapes. Optional language-model generation uses a schema prompt and zero-shot, few-shot, or few-shot with a single corrective retry. The database parser rejects statements outside the supported read-only subset and PostgreSQL's planner checks valid candidates before execution.

The ranking methods are BM25, TF-IDF cosine and MiniLM cosine. The dense encoder uses the pinned all-MiniLM-L6-v2 ONNX model and normalized attention-mask mean pooling. The MongoDB Atlas integration can prefilter a vector query on paper IDs. The measured ranking uses exact CPU cosine. [MiniLM model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) · [MongoDB Vector Search](https://www.mongodb.com/docs/vector-search/)

### 3. Corpus and evaluation

The real pilot contains 353 versioned arXiv metadata records with first submissions in 2018–2024 and membership in cs.LG or cs.AI. It combines March API samples from each year with a curated list of anchor papers. OpenAlex DOI resolution supplies author identities, affiliations, venue candidates and observed references. We retain 325 reference edges whose endpoints both match the pilot. This adjacency defines the incoming citation counts in the experiments. The manifest records the arXiv version and OpenAlex record for each work. [arXiv API manual](https://info.arxiv.org/help/api/user-manual.html) · [OpenAlex](https://arxiv.org/abs/2205.01833)

The SQL benchmark contains 25 lookup, 25 join, 25 aggregation and 25 nested or recursive questions. It contains 80 canonical wordings and 20 meaning-preserving paraphrases. Each question has reference SQL authored with independent query formulations where practical. We compare returned rows on the pilot and on a counterfactual snapshot with selected year and citation changes. The joint metric requires both comparisons to succeed. Ordered cases preserve order and other cases compare multisets.

The retrieval benchmark consists of 24 questions and labels of 1 (closely related) or 2 (direct contribution). Sixteen are hybrid and eight are semantic. Retrieval evaluation treats unjudged papers as zero. Five conditions compare lexical and dense retrieval using the same frozen documents. The placement contrast uses the same MiniLM weights and top-five cutoff. We report macro Recall@5 and nDCG@5, the fraction of returned papers meeting metadata constraints and per-query output length. The paired interval uses 10,000 resamples of the 16 hybrid queries.

For performance, a synthetic fixture populates the supplied schema with 50,000 papers, 18,000 authors and 199,886 citation edges. We compare baseline constraint indexes with the condition that adds the supplied secondary indexes. Ten query cases are timed under a warm-cache ABBA design with 40 measurements per query and condition. The rerun script checks denotation equality and records EXPLAIN ANALYZE with buffers separately. [PostgreSQL EXPLAIN](https://www.postgresql.org/docs/17/sql-explain.html)

### 4. Results

| Hybrid retrieval condition | Recall@5 | nDCG@5 | Eligible papers | Mean returned |
| --- | ---: | ---: | ---: | ---: |
| BM25 + SQL prefilter | 0.776 | 0.815 | 100.0% | 4.88 |
| TF-IDF + SQL prefilter | 0.797 | 0.779 | 100.0% | 4.88 |
| MiniLM alone | 0.583 | 0.612 | 47.5% | 5.00 |
| MiniLM + top-five postfilter | 0.583 | 0.677 | 100.0% | 2.38 |
| MiniLM + SQL prefilter | 0.750 | 0.758 | 100.0% | 5.00 |

The MiniLM comparison isolates filter placement at the same global cutoff. Moving the constraint before ranking recovered 0.167 absolute Recall@5 and increased the mean returned list length. Lexical methods that use the same eligibility constraint ranked strongly on this small set. Results for all 24 cases and raw ranking lists are in `results/`.

| SQL evaluation | Correct on both snapshots | Questions |
| --- | ---: | ---: |
| Lookup | 20 | 25 |
| Joins | 20 | 25 |
| Aggregation | 20 | 25 |
| Nested and recursive | 20 | 25 |
| Overall | 80 | 100 |

The compiler matched all canonical wordings and abstained on each paraphrase. Seventy-three gold answers changed between snapshots. This experiment characterizes a pattern-based baseline with bounded language coverage. The optional LLM prompt strategies are implemented and have a reproducible runner. Provider measurements remain open.

| Selected PostgreSQL workloads | Baseline median (ms) | Indexed median (ms) |
| --- | ---: | ---: |
| Fuzzy author match | 25.314 | 0.423 |
| Top citation ranking | 8.678 | 0.210 |
| Title substring | 14.530 | 0.436 |
| Papers by author | 9.221 | 0.305 |
| Topic trend aggregation | 108.585 | 106.811 |

The relative gains varied by query. The indexed trigram and selective access paths helped the fuzzy and title queries. The full trends aggregate still read a broad input, while the materialized trend view served previously computed results. Report both latency conditions and the query plans for each case when discussing performance.

### 5. Limitations and replication

The pilot overrepresents the selected months and anchors. The in-corpus graph is incomplete relative to the scholarly citation network. The relevance labels come from one annotation pass over a small question set. The fixed top-five postfilter is one baseline, and a production system can choose larger candidate pools. The warm-cache benchmark uses synthetic data and measures read latency on one environment. A larger source harvest, second-rater relevance review, postfilter candidate-pool sweep, and live LLM ablations would extend external validity.

The included `data/` directory provides the corpus and snapshot inputs, benchmark questions, gold SQL, provenance and relevance judgments. `results/` contains the per-case CSV files and query plans. `paper/REPRODUCE.md` lists the commands for rerunning them. The figure and tables in the companion research brief use these outputs.
