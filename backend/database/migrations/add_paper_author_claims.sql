-- Record which paper-author links were claimed on Hugging Face.
--
-- Name matching never attaches new papers to an author linked to an HF
-- account; only claims do. Author pages list every linked paper, claimed or not.
--
-- Run as the schema owner (postgres). Idempotent — safe to re-run.

BEGIN;

SET LOCAL search_path = public;

-- A constant default makes this a metadata-only change, even on a big table.
ALTER TABLE paper_authors
    ADD COLUMN IF NOT EXISTS claimed BOOLEAN NOT NULL DEFAULT false;

COMMIT;
