-- Migration: share one bootstrap bundle per release across curation jobs
--
-- Every paper-curation job used to keep its own ~100 KB copy of the remote
-- worker's bootstrap files, although all jobs bound to one release receive the
-- same bundle. `paper_curation_bootstrap_bundles` stores each distinct bundle
-- once under the SHA-256 of its canonical JSON, and jobs reference it through
-- `bootstrap_bundle_sha256`. A one-off backfill moved the legacy per-job
-- copies; `drop_curation_legacy_bootstrap_bundle.sql` drops that column.
--
-- Run as the schema owner (postgres) before deploying the release that maps the
-- new column. `public` only: the staging job table has no bootstrap bundle.
-- Idempotent: safe to re-run.

BEGIN;

CREATE TABLE IF NOT EXISTS public.paper_curation_bootstrap_bundles (
    sha256 VARCHAR(64) PRIMARY KEY,
    bundle JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.paper_curation_bootstrap_bundles OWNER TO paperswithcode_user;

ALTER TABLE public.paper_curation_jobs
    ADD COLUMN IF NOT EXISTS bootstrap_bundle_sha256 VARCHAR(64)
        REFERENCES public.paper_curation_bootstrap_bundles(sha256);

COMMENT ON TABLE public.paper_curation_bootstrap_bundles IS
'Content-addressed remote curation worker bootstrap snapshots, shared by every job bound to the same bundle.';

COMMENT ON COLUMN public.paper_curation_jobs.bootstrap_bundle_sha256 IS
'Key of the hash-validated bootstrap snapshot bound before dispatch.';

COMMIT;
