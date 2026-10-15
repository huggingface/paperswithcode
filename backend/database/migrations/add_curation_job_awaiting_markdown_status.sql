-- Migration: admin curation jobs can wait for paper Markdown
--
-- An admin-triggered add-evals or enrich-paper job whose first attempt finds no
-- paper text is parked as `awaiting_markdown` instead of failing, and the hourly
-- HF daily-curation reconciliation requeues it once the OCR Markdown exists.
--
-- Run as the schema owner (postgres) before deploying the release that writes
-- the new status. Updates `public` and, when present, the `staging` copy, which
-- uses the same constraint name. Idempotent: safe to re-run.

BEGIN;

ALTER TABLE public.paper_curation_jobs
    DROP CONSTRAINT IF EXISTS paper_curation_jobs_status_check;
ALTER TABLE public.paper_curation_jobs
    ADD CONSTRAINT paper_curation_jobs_status_check
    CHECK (status IN (
        'queued', 'dispatching', 'running', 'completed', 'failed', 'canceled',
        'awaiting_markdown'
    ));

DO $$
BEGIN
    IF to_regclass('staging.paper_curation_jobs') IS NOT NULL THEN
        ALTER TABLE staging.paper_curation_jobs
            DROP CONSTRAINT IF EXISTS paper_curation_jobs_status_check;
        ALTER TABLE staging.paper_curation_jobs
            ADD CONSTRAINT paper_curation_jobs_status_check
            CHECK (status IN (
                'queued', 'dispatching', 'running', 'completed', 'failed',
                'canceled', 'awaiting_markdown'
            ));
    END IF;
END
$$;

COMMIT;
