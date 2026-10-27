-- Verified Google Scholar profiles for authors, with the evidence behind each.
--
-- A row exists only when papers prove the profile belongs to the author (see
-- backend/services/google_scholar_link_service.py); name matches alone never
-- create one. Deleting the author removes the link.
--
-- Run as the schema owner (postgres). Idempotent — safe to re-run.

BEGIN;

SET LOCAL search_path = public;

CREATE TABLE IF NOT EXISTS author_google_scholar_profiles (
    author_id BIGINT PRIMARY KEY REFERENCES authors(id) ON DELETE CASCADE,
    scholar_id VARCHAR(12) NOT NULL UNIQUE,
    -- Where the candidate came from, e.g. Wikidata item 'Q94960976'.
    wikidata_qid VARCHAR(20),
    -- What proved it: 'serpapi' (the profile lists the author's papers).
    evidence_source VARCHAR(30) NOT NULL,
    matched_papers INTEGER NOT NULL,
    considered_papers INTEGER NOT NULL,
    matched_paper_ids BIGINT[] NOT NULL,
    verified_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE author_google_scholar_profiles OWNER TO paperswithcode_user;

DO $$
BEGIN
    IF to_regrole('pwc_staging') IS NOT NULL THEN
        GRANT SELECT ON author_google_scholar_profiles TO pwc_staging;
    END IF;
END $$;

COMMIT;
