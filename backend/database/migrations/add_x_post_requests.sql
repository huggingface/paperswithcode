-- Migration: admin "Tweet it" requests for the Papers with Code X account
--
-- An admin clicks "Tweet it" on a paper page; the X agent drafts the paper
-- and puts it at the front of its post queue, in request order. A request is
-- resolved when the post goes out ('posted'), the admin cancels it
-- ('cancelled'), or the post is removed from the queue ('removed').
--
-- Run as the schema owner (postgres) for `public` before deploying.
-- Idempotent: safe to re-run.

BEGIN;

CREATE TABLE IF NOT EXISTS public.x_post_requests (
    paper_id BIGINT PRIMARY KEY REFERENCES public.papers(id) ON DELETE CASCADE,
    requested_by TEXT,
    requested_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    resolution TEXT
);

CREATE INDEX IF NOT EXISTS idx_x_post_requests_open
    ON public.x_post_requests (requested_at)
    WHERE resolved_at IS NULL;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.x_post_requests
    TO paperswithcode_user;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
        GRANT SELECT ON TABLE public.x_post_requests TO pwc_staging;
    END IF;
END
$$;

COMMENT ON TABLE public.x_post_requests IS
'Admin "Tweet it" requests: papers the X agent posts next, in request order.';

COMMIT;
