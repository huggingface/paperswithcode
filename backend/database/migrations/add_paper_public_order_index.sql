-- Public paper listings ordered by trending: method, task, homepage, and other
-- discovery pages. 98% of papers have no trending score, so the old
-- single-column index forced PostgreSQL to read and sort that whole NULL group
-- (and decompress every abstract for the eligibility check) whenever an entity
-- had fewer than 20 trending papers; /methods/dropout took 2.5 s.
--
-- The key matches the full ORDER BY, so the scan stops after LIMIT matches,
-- and the predicate is eligible_paper_filter() verbatim, so PostgreSQL proves
-- eligibility from the index instead of reading each row. Keep both in sync
-- with backend/services/sitemap_service.py and _papers_for_relation().
--
-- Execute outside a transaction as postgres.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_papers_public_trending_order
ON papers (trending_score DESC NULLS LAST, date_published DESC NULLS LAST, id DESC)
WHERE is_latest_version
  AND length(trim(title)) > 0
  AND length(trim(coalesce(abstract, ''))) > 0
  AND (
    (source = 'arxiv' AND arxiv_id IS NOT NULL)
    OR (source = 'external' AND source_url IS NOT NULL)
  );
