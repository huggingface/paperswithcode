-- Drop two full-text GIN indexes on papers that no query uses (~116 MB).
--
-- idx_papers_abstract_search (to_tsvector('english', abstract), 98 MB) and
-- idx_papers_title_search (to_tsvector('english', title), 18 MB) had 0 scans
-- since the cluster was created. Paper search uses the latest-version
-- search_vector, trigram and normalized-title indexes instead, and no code
-- queries an English tsvector of the raw title or abstract.
--
-- Run outside a transaction (DROP INDEX CONCURRENTLY does not block writes).
DROP INDEX CONCURRENTLY IF EXISTS public.idx_papers_abstract_search;
DROP INDEX CONCURRENTLY IF EXISTS public.idx_papers_title_search;
