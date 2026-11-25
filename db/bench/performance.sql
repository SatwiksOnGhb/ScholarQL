-- Run with psql after loading the same dataset in both conditions.
-- Record PostgreSQL version, CPU/RAM, paper/citation counts, and cache state.
-- Suggested invocation: psql "$env:DATABASE_URL" -f db/bench/performance.sql

ANALYZE;

-- 1. Year/venue filter plus author join
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT p.paper_id, p.title, a.name
FROM paper p
JOIN authorship au USING (paper_id)
JOIN author a USING (author_id)
WHERE p.publication_year BETWEEN 2020 AND 2024
  AND p.venue_id = 'V-SAMPLE-1'
ORDER BY p.publication_year DESC LIMIT 100;

-- 2. Citation count ranking
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT paper_id, title, cited_by_count
FROM paper WHERE publication_year >= 2020
ORDER BY cited_by_count DESC LIMIT 50;

-- 3. Recursive citation traversal
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT * FROM citation_chain('P-SAMPLE-1', 3);

-- 4. Fuzzy author value linking
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT author_id, name, similarity(name, 'Ada Exampel') AS score
FROM author WHERE name % 'Ada Exampel'
ORDER BY score DESC LIMIT 10;

-- 5. Topic trend aggregation (compare base query with the materialized view)
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT t.topic_id, t.name, p.publication_year, count(DISTINCT p.paper_id)
FROM paper p JOIN paper_topic pt USING (paper_id) JOIN topic t USING (topic_id)
GROUP BY t.topic_id, t.name, p.publication_year;

EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT topic_id, topic_name, publication_year, paper_count FROM topic_year_trends;

-- 6. Author publication counts
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT a.author_id, a.name, count(*)
FROM author a JOIN authorship au USING (author_id) JOIN paper p USING (paper_id)
WHERE p.publication_year >= 2020 GROUP BY a.author_id, a.name ORDER BY count(*) DESC LIMIT 50;

-- 7. DOI lookup
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT paper_id, title, publication_year FROM paper WHERE doi = '10.0000/example';

-- 8. Incoming citations for a paper
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT c.citing_id, p.title FROM citation c JOIN paper p ON p.paper_id=c.citing_id
WHERE c.cited_id = 'P-SAMPLE-1';

-- 9. Institution collaboration totals
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT i.institution_id, i.name, count(DISTINCT aa.paper_id)
FROM institution i JOIN author_affiliation aa USING (institution_id)
JOIN paper p USING (paper_id) WHERE p.publication_year >= 2020
GROUP BY i.institution_id, i.name ORDER BY count(DISTINCT aa.paper_id) DESC LIMIT 30;

-- 10. Venue/year publication totals
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT v.venue_id, v.name, p.publication_year, count(*)
FROM paper p JOIN venue v USING (venue_id)
WHERE p.publication_year BETWEEN 2020 AND 2024
GROUP BY v.venue_id, v.name, p.publication_year ORDER BY count(*) DESC LIMIT 100;
