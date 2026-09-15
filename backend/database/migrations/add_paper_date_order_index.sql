-- Match the newest-first feed's ordering without moving undated papers first.
-- Keep the existing date index for queries with other ordering requirements.
-- Run outside a transaction. Check pg_index.indisvalid after completion;
-- IF NOT EXISTS does not repair an invalid index left by an interrupted build.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_papers_date_published_desc_nulls_last
ON public.papers (date_published DESC NULLS LAST);
