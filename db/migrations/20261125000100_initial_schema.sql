-- migrate:up

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE institution (
    institution_id text PRIMARY KEY,
    name text NOT NULL CHECK (length(trim(name)) > 0),
    country_code char(2),
    ror_id text UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE venue (
    venue_id text PRIMARY KEY,
    name text NOT NULL CHECK (length(trim(name)) > 0),
    venue_type text NOT NULL DEFAULT 'unknown'
        CHECK (venue_type IN ('conference', 'journal', 'repository', 'book_series', 'unknown')),
    issn text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE author (
    author_id text PRIMARY KEY,
    name text NOT NULL CHECK (length(trim(name)) > 0),
    orcid text,
    h_index integer CHECK (h_index IS NULL OR h_index >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE topic (
    topic_id text PRIMARY KEY,
    name text NOT NULL CHECK (length(trim(name)) > 0),
    parent_topic_id text REFERENCES topic(topic_id) ON DELETE SET NULL,
    level smallint CHECK (level IS NULL OR level BETWEEN 0 AND 4),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (parent_topic_id IS NULL OR parent_topic_id <> topic_id)
);

CREATE TABLE paper (
    paper_id text PRIMARY KEY,
    title text NOT NULL CHECK (length(trim(title)) > 0),
    publication_year smallint CHECK (publication_year IS NULL OR publication_year BETWEEN 1800 AND 2100),
    publication_date date,
    arxiv_id text,
    doi text,
    venue_id text REFERENCES venue(venue_id) ON DELETE SET NULL,
    cited_by_count integer NOT NULL DEFAULT 0 CHECK (cited_by_count >= 0),
    pagerank_score double precision NOT NULL DEFAULT 0 CHECK (pagerank_score >= 0),
    openalex_updated_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (doi IS NULL OR length(trim(doi)) > 0),
    CHECK (arxiv_id IS NULL OR length(trim(arxiv_id)) > 0)
);

CREATE TABLE authorship (
    paper_id text NOT NULL REFERENCES paper(paper_id) ON DELETE CASCADE,
    author_id text NOT NULL REFERENCES author(author_id) ON DELETE CASCADE,
    author_order smallint NOT NULL CHECK (author_order > 0),
    PRIMARY KEY (paper_id, author_id),
    UNIQUE (paper_id, author_order)
);

CREATE TABLE author_affiliation (
    paper_id text NOT NULL,
    author_id text NOT NULL,
    institution_id text NOT NULL REFERENCES institution(institution_id) ON DELETE CASCADE,
    PRIMARY KEY (paper_id, author_id, institution_id),
    FOREIGN KEY (paper_id, author_id) REFERENCES authorship(paper_id, author_id) ON DELETE CASCADE
);

CREATE TABLE paper_topic (
    paper_id text NOT NULL REFERENCES paper(paper_id) ON DELETE CASCADE,
    topic_id text NOT NULL REFERENCES topic(topic_id) ON DELETE CASCADE,
    relevance double precision CHECK (relevance IS NULL OR relevance BETWEEN 0 AND 1),
    is_primary boolean NOT NULL DEFAULT false,
    PRIMARY KEY (paper_id, topic_id)
);

CREATE UNIQUE INDEX paper_one_primary_topic ON paper_topic(paper_id) WHERE is_primary;

CREATE TABLE citation (
    citing_id text NOT NULL REFERENCES paper(paper_id) ON DELETE CASCADE,
    cited_id text NOT NULL REFERENCES paper(paper_id) ON DELETE CASCADE,
    source text NOT NULL DEFAULT 'openalex' CHECK (source IN ('openalex', 'semantic_scholar', 'arxiv', 'other')),
    PRIMARY KEY (citing_id, cited_id),
    CHECK (citing_id <> cited_id)
);

CREATE INDEX paper_year_venue_idx ON paper(publication_year, venue_id);
CREATE INDEX paper_venue_year_idx ON paper(venue_id, publication_year);
CREATE UNIQUE INDEX paper_doi_unique_idx ON paper(doi) WHERE doi IS NOT NULL;
CREATE UNIQUE INDEX paper_arxiv_unique_idx ON paper(arxiv_id) WHERE arxiv_id IS NOT NULL;
CREATE INDEX paper_cited_by_idx ON paper(cited_by_count DESC);
CREATE INDEX authorship_author_paper_idx ON authorship(author_id, paper_id);
CREATE INDEX authorship_paper_order_idx ON authorship(paper_id, author_order);
CREATE INDEX citation_cited_idx ON citation(cited_id, citing_id);
CREATE INDEX citation_citing_idx ON citation(citing_id, cited_id);
CREATE INDEX paper_title_trgm_idx ON paper USING gin (title gin_trgm_ops);
CREATE INDEX author_name_trgm_idx ON author USING gin (name gin_trgm_ops);
CREATE INDEX venue_name_trgm_idx ON venue USING gin (name gin_trgm_ops);

CREATE FUNCTION maintain_cited_by_count() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE paper SET cited_by_count = cited_by_count + 1 WHERE paper_id = NEW.cited_id;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE paper SET cited_by_count = greatest(cited_by_count - 1, 0) WHERE paper_id = OLD.cited_id;
        RETURN OLD;
    ELSIF OLD.cited_id IS DISTINCT FROM NEW.cited_id THEN
        UPDATE paper SET cited_by_count = greatest(cited_by_count - 1, 0) WHERE paper_id = OLD.cited_id;
        UPDATE paper SET cited_by_count = cited_by_count + 1 WHERE paper_id = NEW.cited_id;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER citation_count_after_write
AFTER INSERT OR UPDATE OR DELETE ON citation
FOR EACH ROW EXECUTE FUNCTION maintain_cited_by_count();

CREATE FUNCTION citation_chain(p_paper_id text, p_depth integer)
RETURNS TABLE(level integer, citing_id text, cited_id text, path text[])
LANGUAGE sql STABLE AS $$
    WITH RECURSIVE walk(level, citing_id, cited_id, path) AS (
        SELECT 1, c.citing_id, c.cited_id, ARRAY[c.citing_id, c.cited_id]::text[]
        FROM citation c
        WHERE c.citing_id = p_paper_id AND p_depth >= 1
        UNION ALL
        SELECT w.level + 1, c.citing_id, c.cited_id, w.path || c.cited_id
        FROM walk w
        JOIN citation c ON c.citing_id = w.cited_id
        WHERE w.level < least(greatest(p_depth, 0), 20)
          AND NOT c.cited_id = ANY(w.path)
    )
    SELECT walk.level, walk.citing_id, walk.cited_id, walk.path FROM walk;
$$;

CREATE FUNCTION coauthors(p_author_id text)
RETURNS TABLE(coauthor_id text, coauthor_name text, shared_papers bigint)
LANGUAGE sql STABLE AS $$
    SELECT other.author_id, a.name, count(DISTINCT mine.paper_id) AS shared_papers
    FROM authorship mine
    JOIN authorship other ON other.paper_id = mine.paper_id AND other.author_id <> mine.author_id
    JOIN author a ON a.author_id = other.author_id
    WHERE mine.author_id = p_author_id
    GROUP BY other.author_id, a.name
    ORDER BY shared_papers DESC, a.name;
$$;

CREATE MATERIALIZED VIEW topic_year_trends AS
SELECT t.topic_id, t.name AS topic_name, p.publication_year,
       count(DISTINCT pt.paper_id)::bigint AS paper_count
FROM paper_topic pt
JOIN topic t USING (topic_id)
JOIN paper p USING (paper_id)
WHERE p.publication_year IS NOT NULL
GROUP BY t.topic_id, t.name, p.publication_year;
CREATE UNIQUE INDEX topic_year_trends_pk ON topic_year_trends(topic_id, publication_year);

CREATE MATERIALIZED VIEW author_stats AS
SELECT a.author_id, a.name, count(DISTINCT au.paper_id)::bigint AS paper_count,
       coalesce(sum(p.cited_by_count), 0)::bigint AS summed_citations,
       max(p.publication_year) AS latest_publication_year
FROM author a
LEFT JOIN authorship au USING (author_id)
LEFT JOIN paper p USING (paper_id)
GROUP BY a.author_id, a.name;
CREATE UNIQUE INDEX author_stats_pk ON author_stats(author_id);

CREATE PROCEDURE refresh_analytics()
LANGUAGE plpgsql AS $$
BEGIN
    REFRESH MATERIALIZED VIEW topic_year_trends;
    REFRESH MATERIALIZED VIEW author_stats;
END;
$$;

CREATE PROCEDURE compute_pagerank(p_iterations integer DEFAULT 30, p_damping double precision DEFAULT 0.85)
LANGUAGE plpgsql AS $$
DECLARE
    n bigint;
    iteration integer;
BEGIN
    IF p_iterations < 1 OR p_iterations > 500 THEN
        RAISE EXCEPTION 'iterations must be between 1 and 500';
    END IF;
    IF p_damping <= 0 OR p_damping >= 1 THEN
        RAISE EXCEPTION 'damping must be between 0 and 1';
    END IF;
    SELECT count(*) INTO n FROM paper;
    IF n = 0 THEN RETURN; END IF;

    CREATE TEMP TABLE pagerank_work (
        paper_id text PRIMARY KEY,
        score double precision NOT NULL,
        next_score double precision NOT NULL
    ) ON COMMIT DROP;
    INSERT INTO pagerank_work SELECT paper_id, 1.0 / n, 1.0 / n FROM paper;

    FOR iteration IN 1..p_iterations LOOP
        WITH out_degree AS (
            SELECT citing_id AS paper_id, count(*)::double precision AS degree
            FROM citation GROUP BY citing_id
        ), dangling AS (
            SELECT coalesce(sum(w.score), 0) AS mass
            FROM pagerank_work w LEFT JOIN out_degree d USING (paper_id)
            WHERE d.paper_id IS NULL
        ), inbound AS (
            SELECT c.cited_id AS paper_id,
                   sum(src.score / d.degree) AS contribution
            FROM citation c
            JOIN pagerank_work src ON src.paper_id = c.citing_id
            JOIN out_degree d ON d.paper_id = c.citing_id
            GROUP BY c.cited_id
        )
        UPDATE pagerank_work target
        SET next_score = (1.0 - p_damping) / n
            + p_damping * (coalesce(inbound.contribution, 0) + (dangling.mass / n))
        FROM dangling LEFT JOIN inbound ON true
        WHERE target.paper_id = inbound.paper_id OR inbound.paper_id IS NULL;

        -- Rows without inbound links still need their base and dangling-mass terms.
        UPDATE pagerank_work target
        SET next_score = (1.0 - p_damping) / n + p_damping * (dangling.mass / n)
        FROM (
            SELECT coalesce(sum(w.score), 0) AS mass
            FROM pagerank_work w
            WHERE NOT EXISTS (SELECT 1 FROM citation c WHERE c.citing_id = w.paper_id)
        ) dangling
        WHERE NOT EXISTS (SELECT 1 FROM citation c WHERE c.cited_id = target.paper_id);

        UPDATE pagerank_work SET score = next_score;
    END LOOP;

    UPDATE paper p SET pagerank_score = w.score FROM pagerank_work w WHERE p.paper_id = w.paper_id;
    DROP TABLE pagerank_work;
END;
$$;

-- migrate:down
DROP PROCEDURE IF EXISTS compute_pagerank(integer, double precision);
DROP PROCEDURE IF EXISTS refresh_analytics();
DROP MATERIALIZED VIEW IF EXISTS author_stats;
DROP MATERIALIZED VIEW IF EXISTS topic_year_trends;
DROP TRIGGER IF EXISTS citation_count_after_write ON citation;
DROP FUNCTION IF EXISTS coauthors(text);
DROP FUNCTION IF EXISTS citation_chain(text, integer);
DROP FUNCTION IF EXISTS maintain_cited_by_count();
DROP TABLE IF EXISTS author_affiliation;
DROP TABLE IF EXISTS authorship;
DROP TABLE IF EXISTS citation;
DROP TABLE IF EXISTS paper_topic;
DROP TABLE IF EXISTS paper;
DROP TABLE IF EXISTS topic;
DROP TABLE IF EXISTS author;
DROP TABLE IF EXISTS venue;
DROP TABLE IF EXISTS institution;
