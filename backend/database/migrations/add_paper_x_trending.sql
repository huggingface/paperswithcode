-- Migration: papers trending on X
--
-- Adds `paper_x_trending`, one row per paper on each day's tab of the
-- "AI Papers on X" sheet. The daily sheet import replaces a day's rows through
-- `PUT /api/v1/papers/x-trending/{shared_on}`; the homepage "trending (X)"
-- tab lists these papers by trending score.
--
-- Run as the schema owner (postgres) once for `public`.

BEGIN;

CREATE TABLE IF NOT EXISTS public.paper_x_trending (
    shared_on DATE NOT NULL,
    paper_id BIGINT NOT NULL REFERENCES public.papers(id) ON DELETE CASCADE,
    rank INTEGER NOT NULL,
    post_url VARCHAR(500),
    post_author VARCHAR(64),
    like_count INTEGER,
    repost_count INTEGER,
    view_count BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (shared_on, paper_id)
);

CREATE INDEX IF NOT EXISTS ix_paper_x_trending_paper_id
    ON public.paper_x_trending (paper_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.paper_x_trending
    TO paperswithcode_user;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
        GRANT SELECT ON TABLE public.paper_x_trending TO pwc_staging;
    END IF;
END
$$;

COMMENT ON TABLE public.paper_x_trending IS
'Papers on each day''s "AI Papers on X" sheet tab, with their top post''s reach.';

COMMIT;
