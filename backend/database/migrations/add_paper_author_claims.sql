-- Record which paper-author links were claimed on Hugging Face.
--
-- Authors linked to an HF account list only the papers they claimed; papers
-- matched by name alone belong to a separate, name-only author row. Run
-- split_unclaimed_hf_author_papers.sql after backfilling claims with
-- `sync_hf_author_profiles --days 10000`.
--
-- Run as the schema owner (postgres). Idempotent — safe to re-run.

BEGIN;

SET LOCAL search_path = public;

-- A constant default makes this a metadata-only change, even on a big table.
ALTER TABLE paper_authors
    ADD COLUMN IF NOT EXISTS claimed BOOLEAN NOT NULL DEFAULT false;

COMMIT;
