-- Migration: X (formerly Twitter) threads on paper pages
--
-- Adds the paper-scoped `paper_x_threads` catalog table, which stores the X
-- posts in which authors introduce a paper together with a preview snapshot
-- captured when the post was linked, and allows `x_threads` pending edits.
--
-- Run as the schema owner (postgres) once for `public`, then once more with
-- `SET search_path = staging, public` so the staging pending-edit constraint
-- matches. The table statements are idempotent no-ops on the second run.

BEGIN;

CREATE TABLE IF NOT EXISTS public.paper_x_threads (
    paper_id BIGINT NOT NULL REFERENCES public.papers(id) ON DELETE CASCADE,
    tweet_id VARCHAR(32) NOT NULL,
    position INTEGER NOT NULL,
    url VARCHAR(500) NOT NULL,
    author_name VARCHAR(255) NOT NULL,
    author_handle VARCHAR(64) NOT NULL,
    author_avatar_url VARCHAR(1000),
    text TEXT NOT NULL,
    posted_at TIMESTAMPTZ,
    like_count INTEGER,
    reply_count INTEGER,
    media_url VARCHAR(1000),
    media_type VARCHAR(16),
    fetched_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (paper_id, tweet_id)
);

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.paper_x_threads
    TO paperswithcode_user;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
        GRANT SELECT ON TABLE public.paper_x_threads TO pwc_staging;
    END IF;
END
$$;

COMMENT ON TABLE public.paper_x_threads IS
'X posts introducing a paper, with a preview snapshot taken when linked.';

ALTER TABLE pending_paper_edits
    DROP CONSTRAINT IF EXISTS pending_paper_edits_edit_type_check;

ALTER TABLE pending_paper_edits
    ADD CONSTRAINT pending_paper_edits_edit_type_check CHECK (
        edit_type IN (
            'tasks',
            'methods',
            'evaluations',
            'repositories',
            'project_pages',
            'source_url',
            'hf_artifacts',
            'organizations',
            'x_threads',
            'new_task',
            'new_method',
            'new_benchmark',
            'new_metric',
            'new_conference',
            'new_external_paper'
        )
    );

COMMIT;
