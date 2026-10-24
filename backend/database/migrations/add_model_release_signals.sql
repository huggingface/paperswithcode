-- Migration: release-radar signals and their resolution jobs
--
-- Lets the `scan_model_releases` CRON record each model release that no
-- paper covers (`model_release_signals`) and queue one scoped
-- `resolve-model-paper` curation job per signal (trigger
-- `model-release-radar`). The job finds the lab's own announcement and
-- resolves it to an existing, arXiv, or new external paper.
--
-- Run as the schema owner (postgres) before deploying the release that reads
-- these columns. Updates `public` and, when present, adds the new job column
-- to the `staging` copy, which keeps its own trigger and scope checks.
-- Idempotent: safe to re-run.

BEGIN;

CREATE TABLE IF NOT EXISTS public.model_release_signals (
    id UUID PRIMARY KEY,
    signal_key TEXT NOT NULL UNIQUE,
    lab VARCHAR(255) NOT NULL,
    model_name TEXT NOT NULL,
    title TEXT NOT NULL,
    lead_url TEXT NOT NULL,
    source TEXT NOT NULL,
    lead_is_official BOOLEAN NOT NULL DEFAULT false,
    published DATE,
    sightings INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(24) NOT NULL DEFAULT 'discovered',
    rejection_reason TEXT,
    paper_id BIGINT REFERENCES public.papers(id) ON DELETE SET NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ,
    CONSTRAINT model_release_signals_status_check
        CHECK (status IN ('discovered', 'queued', 'resolving', 'resolved', 'rejected', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_model_release_signals_status
    ON public.model_release_signals (status, last_seen_at);

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.model_release_signals
    TO paperswithcode_user;

ALTER TABLE public.paper_curation_jobs
    ADD COLUMN IF NOT EXISTS release_signal_id UUID
        REFERENCES public.model_release_signals(id) ON DELETE CASCADE;

ALTER TABLE public.paper_curation_jobs
    DROP CONSTRAINT IF EXISTS paper_curation_jobs_trigger_check;
ALTER TABLE public.paper_curation_jobs
    ADD CONSTRAINT paper_curation_jobs_trigger_check
    CHECK (trigger IN (
        'admin', 'hf-daily-cron', 'hf-trending-cron', 'benchmark-promotion',
        'benchmark-gap-cron', 'model-release-radar'
    ));

ALTER TABLE public.paper_curation_jobs
    DROP CONSTRAINT IF EXISTS paper_curation_jobs_scope_check;
ALTER TABLE public.paper_curation_jobs
    ADD CONSTRAINT paper_curation_jobs_scope_check
    CHECK (
        (kind = 'resolve-model-paper' AND paper_id IS NULL
            AND benchmark_candidate_id IS NULL
            AND (candidate_id IS NULL) <> (release_signal_id IS NULL))
        OR (kind = 'add-benchmark' AND benchmark_candidate_id IS NOT NULL
            AND paper_id IS NULL AND candidate_id IS NULL
            AND release_signal_id IS NULL)
        OR (kind = 'review-benchmark-gaps' AND paper_id IS NULL
            AND candidate_id IS NULL AND benchmark_candidate_id IS NULL
            AND release_signal_id IS NULL)
        OR (kind IN ('add-evals', 'enrich-paper') AND paper_id IS NOT NULL
            AND candidate_id IS NULL AND benchmark_candidate_id IS NULL
            AND release_signal_id IS NULL)
    );

CREATE INDEX IF NOT EXISTS idx_paper_curation_jobs_release_signal
    ON public.paper_curation_jobs (release_signal_id, created_at);

CREATE UNIQUE INDEX IF NOT EXISTS uq_active_release_signal_resolution
    ON public.paper_curation_jobs (release_signal_id)
    WHERE kind = 'resolve-model-paper' AND status IN ('queued', 'dispatching', 'running');

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
        GRANT SELECT ON TABLE public.model_release_signals TO pwc_staging;
    END IF;
    IF to_regclass('staging.paper_curation_jobs') IS NOT NULL THEN
        ALTER TABLE staging.paper_curation_jobs
            ADD COLUMN IF NOT EXISTS release_signal_id UUID;
    END IF;
END
$$;

COMMENT ON TABLE public.model_release_signals IS
'Model releases the scan_model_releases CRON found with no covering paper, and their resolution state.';

COMMIT;
