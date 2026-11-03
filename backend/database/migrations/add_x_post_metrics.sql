-- Migration: X post like velocity for the paper trending score
--
-- `x_post_metrics` keeps one row per X post linked to a paper (a post can be
-- linked to several papers), with its latest like count and smoothed likes per
-- hour. The `refresh_x_post_likes` CRON reads each post on a decaying schedule
-- during its first week; `calculate_paper_trending_scores` reads the velocity.
-- `papers.x_trending_component` stores the normalized X part of the score.
--
-- Run as the schema owner (postgres) for `public` before merging.
-- Idempotent: safe to re-run.

BEGIN;

-- Adding a nullable column is instant, but it needs a brief exclusive lock on
-- the busy papers table; fail fast instead of queueing behind long readers.
SET LOCAL lock_timeout = '10s';

CREATE TABLE IF NOT EXISTS public.x_post_metrics (
    tweet_id VARCHAR(32) PRIMARY KEY,
    posted_at TIMESTAMPTZ NOT NULL,
    like_count INTEGER,
    like_velocity DOUBLE PRECISION,
    last_read_at TIMESTAMPTZ,
    last_source VARCHAR(16),
    read_count INTEGER NOT NULL DEFAULT 0,
    next_read_at TIMESTAMPTZ,
    gone_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_x_post_metrics_next_read_at
    ON public.x_post_metrics (next_read_at)
    WHERE next_read_at IS NOT NULL;

ALTER TABLE public.papers
    ADD COLUMN IF NOT EXISTS x_trending_component NUMERIC(12, 4);

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.x_post_metrics
    TO paperswithcode_user;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
        GRANT SELECT ON TABLE public.x_post_metrics TO pwc_staging;
    END IF;
    -- Same grants deploy/configure_db_roles.py gives the isolated scoring role.
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_cron_trending') THEN
        GRANT SELECT ON TABLE public.paper_x_threads, public.x_post_metrics
            TO pwc_cron_trending;
        GRANT UPDATE (x_trending_component) ON public.papers TO pwc_cron_trending;
    END IF;
END
$$;

COMMENT ON TABLE public.x_post_metrics IS
'Like counts and smoothed likes per hour of linked X posts, from the refresh_x_post_likes CRON.';
COMMENT ON COLUMN public.papers.x_trending_component IS
'Quantile rank (0-1) of the paper''s fastest linked X post in the trending score.';

COMMIT;
