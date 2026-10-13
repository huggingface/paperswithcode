-- Migration: conference deadline sweep ledger
--
-- One row per off-box research sweep launched by the
-- `sweep_conference_deadlines` / `refresh_conference_deadlines` CRONs: the
-- Hugging Face Job, the researched series, what was applied to
-- `conference_deadlines`, and the cost. The CRON dashboard reads the latest
-- applied sweep as the deadline data freshness.
--
-- Run as the schema owner (postgres) for `public` before enabling the timers.
-- Idempotent: safe to re-run.

BEGIN;

CREATE TABLE IF NOT EXISTS public.conference_deadline_sweeps (
    id BIGSERIAL PRIMARY KEY,
    mode VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL,
    hf_job_id VARCHAR(100),
    series JSONB NOT NULL,
    launched_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    changes_applied INTEGER NOT NULL DEFAULT 0,
    cost_usd NUMERIC(10, 4),
    results JSONB,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_conference_deadline_sweeps_status
    ON public.conference_deadline_sweeps (status, finished_at);

GRANT SELECT, INSERT, UPDATE ON TABLE public.conference_deadline_sweeps
    TO paperswithcode_user;
GRANT USAGE, SELECT ON SEQUENCE public.conference_deadline_sweeps_id_seq
    TO paperswithcode_user;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
        GRANT SELECT ON TABLE public.conference_deadline_sweeps TO pwc_staging;
    END IF;
END
$$;

COMMENT ON TABLE public.conference_deadline_sweeps IS
'Off-box conference deadline research sweeps and the changes they applied.';

COMMIT;
