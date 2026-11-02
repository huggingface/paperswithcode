-- Migration: pair scheduled Codex curation stages with Pi shadow runs
--
-- A sampled daily-curation stage gets a second, shadow-only job run by the Pi
-- harness on an open model. `runner` names the agent harness of each job,
-- `paired_job_id` points a Pi shadow job at the Codex job it mirrors,
-- `context_snapshot` freezes the paper context both runners started from, and
-- `pair_diff` stores the per-pair comparison once both jobs are terminal.
--
-- Created: 2026-11-02
-- Usage (as postgres, before deploying the backend that maps the columns):
--   sudo -u postgres psql -d paperswithcode_hf -X -v ON_ERROR_STOP=1 \
--        < backend/database/migrations/add_curation_pi_shadow_runner.sql
-- A constant default makes the NOT NULL column a metadata-only change.
-- Idempotent: safe to re-run.

BEGIN;

SET LOCAL lock_timeout = '10s';

ALTER TABLE public.paper_curation_jobs
    ADD COLUMN IF NOT EXISTS runner VARCHAR(8) NOT NULL DEFAULT 'codex',
    ADD COLUMN IF NOT EXISTS paired_job_id UUID
        REFERENCES public.paper_curation_jobs(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS context_snapshot JSONB,
    ADD COLUMN IF NOT EXISTS pair_diff JSONB;

CREATE INDEX IF NOT EXISTS ix_paper_curation_jobs_paired_job_id
    ON public.paper_curation_jobs (paired_job_id)
    WHERE paired_job_id IS NOT NULL;

COMMENT ON COLUMN public.paper_curation_jobs.runner IS
'Agent harness that ran the job: codex, or pi for shadow-only comparison runs.';

COMMENT ON COLUMN public.paper_curation_jobs.paired_job_id IS
'For a Pi shadow job, the Codex job whose stage and starting context it mirrors.';

COMMENT ON COLUMN public.paper_curation_jobs.context_snapshot IS
'Paper context frozen at pairing time; served to the Pi shadow job instead of live state.';

COMMENT ON COLUMN public.paper_curation_jobs.pair_diff IS
'Comparison of a Pi shadow proposal with its Codex pair, written when both are terminal.';

DO $$
BEGIN
    IF to_regclass('staging.paper_curation_jobs') IS NOT NULL THEN
        ALTER TABLE staging.paper_curation_jobs
            ADD COLUMN IF NOT EXISTS runner VARCHAR(8) NOT NULL DEFAULT 'codex',
            ADD COLUMN IF NOT EXISTS paired_job_id UUID
                REFERENCES staging.paper_curation_jobs(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS context_snapshot JSONB,
            ADD COLUMN IF NOT EXISTS pair_diff JSONB;
    END IF;
END $$;

COMMIT;
