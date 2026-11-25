-- Portable mirror of the supplied PostgreSQL core for the pilot.
CREATE TABLE institution (
    institution_id text PRIMARY KEY,
    name text NOT NULL CHECK (length(trim(name)) > 0),
    country_code char(2),
    ror_id text UNIQUE,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE venue (
    venue_id text PRIMARY KEY,
    name text NOT NULL CHECK (length(trim(name)) > 0),
    venue_type text NOT NULL DEFAULT 'unknown'
        CHECK (venue_type IN ('conference', 'journal', 'repository', 'book_series', 'unknown')),
    issn text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE author (
    author_id text PRIMARY KEY,
    name text NOT NULL CHECK (length(trim(name)) > 0),
    orcid text,
    h_index integer CHECK (h_index IS NULL OR h_index >= 0),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE topic (
    topic_id text PRIMARY KEY,
    name text NOT NULL CHECK (length(trim(name)) > 0),
    parent_topic_id text REFERENCES topic(topic_id) ON DELETE SET NULL,
    level smallint CHECK (level IS NULL OR level BETWEEN 0 AND 4),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
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
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
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

CREATE TRIGGER citation_count_insert AFTER INSERT ON citation BEGIN
    UPDATE paper SET cited_by_count = cited_by_count + 1 WHERE paper_id = NEW.cited_id;
END;
CREATE TRIGGER citation_count_delete AFTER DELETE ON citation BEGIN
    UPDATE paper SET cited_by_count = max(cited_by_count - 1, 0) WHERE paper_id = OLD.cited_id;
END;
CREATE TRIGGER citation_count_update AFTER UPDATE OF cited_id ON citation
WHEN OLD.cited_id <> NEW.cited_id BEGIN
    UPDATE paper SET cited_by_count = max(cited_by_count - 1, 0) WHERE paper_id = OLD.cited_id;
    UPDATE paper SET cited_by_count = cited_by_count + 1 WHERE paper_id = NEW.cited_id;
END;

CREATE VIEW topic_year_trends AS
SELECT t.topic_id, t.name AS topic_name, p.publication_year,
       count(DISTINCT pt.paper_id) AS paper_count
FROM paper_topic pt JOIN topic t USING (topic_id) JOIN paper p USING (paper_id)
WHERE p.publication_year IS NOT NULL
GROUP BY t.topic_id, t.name, p.publication_year;

CREATE VIEW author_stats AS
SELECT a.author_id, a.name, count(DISTINCT au.paper_id) AS paper_count,
       coalesce(sum(p.cited_by_count), 0) AS summed_citations,
       max(p.publication_year) AS latest_publication_year
FROM author a LEFT JOIN authorship au USING (author_id)
LEFT JOIN paper p USING (paper_id) GROUP BY a.author_id, a.name;
