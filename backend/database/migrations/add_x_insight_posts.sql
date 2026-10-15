-- Migration: insight posts on the Papers with Code X account
--
-- Records each SOTA, trending, and roundup post made by the `post_x_insight`
-- CRON, so no subject is posted twice (trending entities may return after 30
-- days).
--
-- Run as the schema owner (postgres) for `public` before enabling the timer.
-- Idempotent: safe to re-run.

BEGIN;

CREATE TABLE IF NOT EXISTS public.x_insight_posts (
    id BIGSERIAL PRIMARY KEY,
    kind TEXT NOT NULL,
    subject_key TEXT NOT NULL,
    post_id TEXT NOT NULL,
    reply_id TEXT,
    posted_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_x_insight_posts_kind_subject
    ON public.x_insight_posts (kind, subject_key);

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.x_insight_posts
    TO paperswithcode_user;
GRANT USAGE, SELECT ON SEQUENCE public.x_insight_posts_id_seq
    TO paperswithcode_user;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
        GRANT SELECT ON TABLE public.x_insight_posts TO pwc_staging;
    END IF;
END
$$;

COMMENT ON TABLE public.x_insight_posts IS
'SOTA, trending, and roundup posts made by the post_x_insight CRON on the Papers with Code X account.';

COMMIT;
