-- Migration: legacy paperswithcode.com slugs
--
-- Maps each /paper/, /sota/, /dataset/ and /method/ slug from the legacy
-- Papers with Code dumps to what it named (an arXiv id for papers, the legacy
-- dataset or method name otherwise). Public routes resolve these against the
-- live catalog and 301 to the current page. Filled by
-- backend/scripts/import_legacy_pwc_slugs.py.
--
-- Additive and idempotent: safe to re-run.

BEGIN;

CREATE TABLE IF NOT EXISTS public.legacy_pwc_slugs (
    kind TEXT NOT NULL CHECK (kind IN ('paper', 'sota', 'dataset', 'method')),
    slug TEXT NOT NULL,
    target TEXT NOT NULL,
    PRIMARY KEY (kind, slug)
);

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.legacy_pwc_slugs
    TO paperswithcode_user;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
        GRANT SELECT ON TABLE public.legacy_pwc_slugs TO pwc_staging;
    END IF;
END
$$;

COMMENT ON TABLE public.legacy_pwc_slugs IS
'Legacy paperswithcode.com slugs: paper -> arXiv id; sota/dataset/method -> legacy name.';

COMMIT;
