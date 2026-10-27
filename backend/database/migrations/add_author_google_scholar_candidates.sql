-- Evidence checked so far for each (author, Wikidata Scholar ID) candidate.
--
-- The weekly `sync_google_scholar_profiles` CRON keeps its progress here: a
-- candidate is checked on Semantic Scholar once, and on the Scholar profile
-- (SerpAPI) once, as the free monthly quota allows. Links themselves live in
-- author_google_scholar_profiles. Deleting the author removes its candidates.
--
-- Run as the schema owner (postgres). Idempotent — safe to re-run.

BEGIN;

SET LOCAL search_path = public;

CREATE TABLE IF NOT EXISTS author_google_scholar_candidates (
    author_id BIGINT NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
    scholar_id VARCHAR(12) NOT NULL,
    wikidata_qid VARCHAR(20) NOT NULL,
    -- Semantic Scholar check: {verdict, considered, matched, share, ...}.
    s2_evidence JSONB NOT NULL,
    -- Scholar profile check through SerpAPI; NULL until one is spent on it.
    serpapi_evidence JSONB,
    s2_checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    serpapi_checked_at TIMESTAMPTZ,
    PRIMARY KEY (author_id, scholar_id, wikidata_qid)
);

ALTER TABLE author_google_scholar_candidates OWNER TO paperswithcode_user;

COMMIT;
