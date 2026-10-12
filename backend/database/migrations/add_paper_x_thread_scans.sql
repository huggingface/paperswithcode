-- Migration: X thread discovery scan state
--
-- Records which papers the `discover_x_threads` CRON has searched on X, so each
-- paper is searched a bounded number of times, plus the matched posts kept for
-- review while the job runs report-only.
--
-- Run as the schema owner (postgres) for `public` before enabling the timer.
-- Idempotent: safe to re-run.

BEGIN;

CREATE TABLE IF NOT EXISTS public.paper_x_thread_scans (
    paper_id BIGINT PRIMARY KEY REFERENCES public.papers(id) ON DELETE CASCADE,
    scan_count INTEGER NOT NULL DEFAULT 0,
    last_scanned_at TIMESTAMPTZ NOT NULL,
    candidates JSONB NOT NULL DEFAULT '[]'::jsonb,
    linked_at TIMESTAMPTZ
);

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.paper_x_thread_scans
    TO paperswithcode_user;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
        GRANT SELECT ON TABLE public.paper_x_thread_scans TO pwc_staging;
    END IF;
END
$$;

COMMENT ON TABLE public.paper_x_thread_scans IS
'X search attempts and author-post matches from the discover_x_threads CRON.';

COMMIT;
