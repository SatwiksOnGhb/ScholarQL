-- Baseline condition: retain primary/unique indexes, remove workload indexes.
DROP INDEX IF EXISTS paper_year_venue_idx;
DROP INDEX IF EXISTS paper_venue_year_idx;
DROP INDEX IF EXISTS paper_cited_by_idx;
DROP INDEX IF EXISTS authorship_author_paper_idx;
DROP INDEX IF EXISTS authorship_paper_order_idx;
DROP INDEX IF EXISTS citation_cited_idx;
DROP INDEX IF EXISTS citation_citing_idx;
DROP INDEX IF EXISTS paper_title_trgm_idx;
DROP INDEX IF EXISTS author_name_trgm_idx;
DROP INDEX IF EXISTS venue_name_trgm_idx;
