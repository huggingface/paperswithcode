-- Migration: drop the redundant evaluations.external_source_url column (#1106)
--
-- Since #1168 the ORM mirrors every source_url write into external_source_url,
-- and the release that ships this file no longer maps the column at all; the
-- API returns external_source_url as an alias of source_url.
--
-- Rows written before #1168 may hold a URL only in external_source_url. The
-- API showed COALESCE(source_url, external_source_url), so copying those URLs
-- into source_url keeps public output unchanged. Run that backfill (the UPDATE
-- below) before deploying the release that stops reading the column; it is
-- repeated here so the drop can never lose a URL. Where both columns are set
-- and differ, source_url is the value the API showed and is kept.
--
-- Run as the schema owner (postgres) only AFTER the release that ships this
-- file is live in production. Idempotent: safe to re-run.

BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'evaluations'
          AND column_name = 'external_source_url'
    ) THEN
        UPDATE public.evaluations
        SET source_url = external_source_url
        WHERE source_url IS NULL
          AND external_source_url IS NOT NULL;

        ALTER TABLE public.evaluations DROP COLUMN external_source_url;
    END IF;
END
$$;

COMMIT;
