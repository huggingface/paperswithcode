-- Planner statistics for the title fingerprint used by POST /papers/lookup.
-- idx_papers_latest_title_fingerprint is a partial index, and PostgreSQL never
-- uses a partial index's statistics for selectivity estimates, so the planner
-- assumed hundreds of rows per fingerprint and switched to a sequential scan
-- once a request carried more than about 50 candidates. Extended expression
-- statistics describe the near-unique distribution directly.
-- Run add_paper_title_fingerprint_index.sql first, as the table owner.
CREATE STATISTICS IF NOT EXISTS papers_title_fingerprint_stats
    ON (regexp_replace(lower(title), '[^a-z0-9]+', '', 'g'))
    FROM papers;

ANALYZE papers;
