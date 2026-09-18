-- Match PDF bibliography entries to catalog papers by title. The fingerprint
-- keeps only ASCII letters and digits so hyphenation, punctuation, spacing, and
-- case differences between a reference entry and the stored title do not matter.
-- Keep the expression identical to title_fingerprint_expression() in
-- backend/services/paper_reference_service.py.
-- Run outside a transaction because CONCURRENTLY cannot run inside one.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_papers_latest_title_fingerprint
ON papers (regexp_replace(lower(title), '[^a-z0-9]+', '', 'g'))
WHERE is_latest_version;
