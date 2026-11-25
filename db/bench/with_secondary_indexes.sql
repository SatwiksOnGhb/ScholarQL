-- Optimized condition: restore the workload indexes from the migration.
CREATE INDEX IF NOT EXISTS paper_year_venue_idx ON paper(publication_year, venue_id);
CREATE INDEX IF NOT EXISTS paper_venue_year_idx ON paper(venue_id, publication_year);
CREATE INDEX IF NOT EXISTS paper_cited_by_idx ON paper(cited_by_count DESC);
CREATE INDEX IF NOT EXISTS authorship_author_paper_idx ON authorship(author_id, paper_id);
CREATE INDEX IF NOT EXISTS authorship_paper_order_idx ON authorship(paper_id, author_order);
CREATE INDEX IF NOT EXISTS citation_cited_idx ON citation(cited_id, citing_id);
CREATE INDEX IF NOT EXISTS citation_citing_idx ON citation(citing_id, cited_id);
CREATE INDEX IF NOT EXISTS paper_title_trgm_idx ON paper USING gin (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS author_name_trgm_idx ON author USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS venue_name_trgm_idx ON venue USING gin (name gin_trgm_ops);
