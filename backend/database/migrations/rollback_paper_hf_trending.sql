-- Rollback: HF-enhanced paper trending
-- Drops the normalized HF artifact tables and the paper composite trending columns.
-- The GitHub-only ranking (repositories.trending_score) is unaffected.

DROP TABLE IF EXISTS paper_hf_artifacts CASCADE;
DROP TABLE IF EXISTS hf_artifacts CASCADE;

DROP INDEX IF EXISTS idx_papers_trending_score;
DROP INDEX IF EXISTS idx_papers_trending_score_updated_at;
DROP INDEX IF EXISTS idx_papers_hf_artifacts_scanned_at;

ALTER TABLE papers DROP COLUMN IF EXISTS trending_score;
ALTER TABLE papers DROP COLUMN IF EXISTS trending_score_updated_at;
ALTER TABLE papers DROP COLUMN IF EXISTS github_trending_component;
ALTER TABLE papers DROP COLUMN IF EXISTS hf_trending_component;
ALTER TABLE papers DROP COLUMN IF EXISTS hf_artifacts_scanned_at;
