-- Store redirects left behind when an external paper is merged into its
-- canonical ArXiv paper.
--
-- This is shared catalog state. Staging may read redirects but must not create
-- or modify them.
\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE IF NOT EXISTS public.paper_redirects (
    old_paper_id BIGINT PRIMARY KEY,
    route_identifier VARCHAR(100) NOT NULL
);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE
            ON public.paper_redirects TO paperswithcode_user;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
        GRANT SELECT ON public.paper_redirects TO pwc_staging;
    END IF;
END $$;

COMMIT;
