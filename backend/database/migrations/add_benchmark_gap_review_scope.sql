-- Migration: freeze the benchmark-gap review batch on its job
--
-- A `review-benchmark-gaps` job records the candidate ids it was served in
-- `paper_curation_jobs.review_scope` and must decide each of them, so ranking
-- changes while the job runs cannot reject a complete review.
--
-- Run as the schema owner (postgres) before deploying the release that reads
-- this column. Updates `public` and, when present, the `staging` copy.
-- Idempotent: safe to re-run.

BEGIN;

ALTER TABLE public.paper_curation_jobs
    ADD COLUMN IF NOT EXISTS review_scope JSONB;

DO $$
BEGIN
    IF to_regclass('staging.paper_curation_jobs') IS NOT NULL THEN
        ALTER TABLE staging.paper_curation_jobs
            ADD COLUMN IF NOT EXISTS review_scope JSONB;
    END IF;
END
$$;

COMMIT;
