-- Migration: drop the legacy per-job curation bootstrap bundle
--
-- `add_curation_bootstrap_bundle_store.sql` moved every job's bundle into
-- `paper_curation_bootstrap_bundles`; jobs now reference it only through
-- `bootstrap_bundle_sha256`. This drops the emptied per-job copy.
--
-- Run as the schema owner (postgres) AFTER the release that no longer maps the
-- column is live in production: older releases still select it. Refuses to run
-- while any job still carries a bundle. `public` only: the staging job table
-- never had the column. Idempotent: safe to re-run.

BEGIN;

DO $$
DECLARE
    remaining boolean;
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'paper_curation_jobs'
          AND column_name = 'bootstrap_bundle'
    ) THEN
        -- Dynamic so a re-run after the drop does not plan a missing column.
        EXECUTE 'SELECT EXISTS (SELECT 1 FROM public.paper_curation_jobs'
            ' WHERE bootstrap_bundle IS NOT NULL)' INTO remaining;
        IF remaining THEN
            RAISE EXCEPTION 'paper_curation_jobs.bootstrap_bundle still holds bundles';
        END IF;
    END IF;
END
$$;

ALTER TABLE public.paper_curation_jobs DROP COLUMN IF EXISTS bootstrap_bundle;

COMMIT;
