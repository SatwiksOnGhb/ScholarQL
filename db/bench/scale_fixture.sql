-- Deterministic synthetic workload. Only run in an empty experiment database.
CREATE TABLE scholarql_index_fixture (version integer PRIMARY KEY, paper_count integer NOT NULL);
INSERT INTO scholarql_index_fixture VALUES (1, 50000);

INSERT INTO institution (institution_id,name,country_code)
SELECT 'I'||i, 'Synthetic Institute '||i, 'IN' FROM generate_series(1,32) i;
INSERT INTO venue (venue_id,name,venue_type)
SELECT 'V'||i, 'Synthetic Venue '||i, 'conference' FROM generate_series(1,256) i;
INSERT INTO topic (topic_id,name,level)
SELECT 'T'||i, 'Synthetic Topic '||i, 1 FROM generate_series(1,32) i;
INSERT INTO author (author_id,name)
SELECT 'A'||i, CASE WHEN i % 997=0 THEN 'Samara Quasar ' ELSE 'Researcher ' END || lpad(i::text,5,'0')
FROM generate_series(1,18000) i;
INSERT INTO paper (paper_id,title,publication_year,publication_date,doi,venue_id)
SELECT 'P'||i, CASE WHEN i % 331=0 THEN 'Quasar representation in ' ELSE 'A study of methods in ' END ||
       substr(md5(i::text),1,14), 2018+(i%7), make_date(2018+(i%7),3,1), '10.0000/study.'||i,
       'V'||(1+((i::bigint*104729)%256))
FROM generate_series(1,50000) i;
INSERT INTO authorship (paper_id,author_id,author_order)
SELECT 'P'||i, 'A'||(1+((i::bigint*15721 + k*9973)%18000)), k
FROM generate_series(1,50000) i CROSS JOIN generate_series(1,3) k;
INSERT INTO author_affiliation (paper_id,author_id,institution_id)
SELECT 'P'||i, 'A'||(1+((i::bigint*15721 + 9973)%18000)), 'I'||(1+(i%32))
FROM generate_series(1,50000) i WHERE i%2=0;
INSERT INTO paper_topic (paper_id,topic_id,is_primary)
SELECT 'P'||i,'T'||(1+(i%32)),true FROM generate_series(1,50000) i;

ALTER TABLE citation DISABLE TRIGGER citation_count_after_write;
INSERT INTO citation (citing_id,cited_id,source)
SELECT 'P'||i, 'P'||target, 'other'
FROM generate_series(20,50000) i CROSS JOIN LATERAL (
    SELECT DISTINCT CASE WHEN k=1 AND i%8=0 THEN 8
           ELSE 1 + ((i::bigint*104729 + 19*k*k*(i%499) + k*1871) % (i-1)) END AS target
    FROM generate_series(1,4) k
) g;
UPDATE paper p SET cited_by_count = totals.n
FROM (SELECT cited_id,count(*) AS n FROM citation GROUP BY cited_id) totals
WHERE p.paper_id=totals.cited_id;
ALTER TABLE citation ENABLE TRIGGER citation_count_after_write;
CALL refresh_analytics();
ANALYZE;
