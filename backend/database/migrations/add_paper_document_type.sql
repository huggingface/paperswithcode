-- Optional reader-facing document type of a paper, such as "Technical Report".
-- Paper pages use it in the search title and lead sentence; NULL means an
-- ordinary paper. Replaces the hard-coded DOCUMENT_TYPE_OVERRIDES map in
-- backend/services/paper_seo_service.py. Additive and idempotent; apply as
-- postgres before deploying code that maps the column.

ALTER TABLE papers ADD COLUMN IF NOT EXISTS document_type VARCHAR(50);

COMMENT ON COLUMN papers.document_type IS
    'Optional document type shown on the paper page, e.g. Technical Report; NULL for an ordinary paper.';

UPDATE papers
SET document_type = 'Technical Report', updated_at = CURRENT_TIMESTAMP
WHERE arxiv_id = '2607.24653'
  AND document_type IS DISTINCT FROM 'Technical Report';
