-- Migration: papers posted to the Papers with Code X account
--
-- Records which papers the `post_trending_paper_to_x` CRON has posted, so each
-- paper is posted at most once.
--
-- Run as the schema owner (postgres) for `public` before enabling the timer.
-- Idempotent: safe to re-run.

BEGIN;

CREATE TABLE IF NOT EXISTS public.paper_x_posts (
    paper_id BIGINT PRIMARY KEY REFERENCES public.papers(id) ON DELETE CASCADE,
    post_id TEXT NOT NULL,
    reply_id TEXT,
    posted_at TIMESTAMPTZ NOT NULL
);

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.paper_x_posts
    TO paperswithcode_user;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
        GRANT SELECT ON TABLE public.paper_x_posts TO pwc_staging;
    END IF;
END
$$;

COMMENT ON TABLE public.paper_x_posts IS
'Papers posted to the Papers with Code X account by the post_trending_paper_to_x CRON.';

COMMIT;
