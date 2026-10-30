-- Migration: Freely licensed author portraits
--
-- Most well-known researchers have no Hugging Face account, so their author
-- pages and the research-feed suggestions showed no face. `author_photos`
-- self-hosts one portrait per author (from Wikimedia Commons) with the credit
-- and license its terms require us to display.
--
-- Created: 2026-10-30
-- Usage (as postgres, before deploying the backend that maps the table):
--   sudo -u postgres psql -d paperswithcode_hf -X -v ON_ERROR_STOP=1 \
--        < backend/database/migrations/add_author_photos.sql

BEGIN;

SET LOCAL lock_timeout = '10s';

CREATE TABLE IF NOT EXISTS public.author_photos (
    author_id BIGINT PRIMARY KEY REFERENCES public.authors(id) ON DELETE CASCADE,
    image_data BYTEA NOT NULL,
    mime_type VARCHAR(50) NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    source_url VARCHAR(1000) NOT NULL,
    credit VARCHAR(500) NOT NULL,
    license VARCHAR(100) NOT NULL,
    license_url VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

ALTER TABLE public.author_photos OWNER TO paperswithcode_user;

DO $$
BEGIN
    IF to_regrole('pwc_staging') IS NOT NULL THEN
        GRANT SELECT ON public.author_photos TO pwc_staging;
    END IF;
END $$;

COMMIT;
