-- Drop two repository_star_history indexes that duplicate other indexes and
-- together hold about 1.2 GB on the space-constrained production disk.
--
-- idx_star_history_repo_time (repository_id, snapshot_at DESC) duplicates the
--   unique (repository_id, snapshot_at) index, which PostgreSQL scans
--   backward for newest-first reads.
-- idx_star_history_snapshot_at (snapshot_at DESC) is the leading column of
--   idx_star_history_recent (snapshot_at DESC, repository_id); it had 14
--   scans since the cluster was created, against 43k for the composite.
--
-- idx_star_history_repository_id is kept: it is small and the trending path
-- reads it billions of times.
--
-- Run outside a transaction (DROP INDEX CONCURRENTLY does not block writes).
DROP INDEX CONCURRENTLY IF EXISTS public.idx_star_history_repo_time;
DROP INDEX CONCURRENTLY IF EXISTS public.idx_star_history_snapshot_at;
