-- Move papers that an HF-linked author never claimed to a name-only author.
--
-- Importers used to match arXiv author names to the row of whoever first
-- claimed that name on Hugging Face, so /authors/<id> of a common name listed
-- every namesake's papers. An author linked to an HF account now holds only
-- the papers its account claimed (paper_authors.claimed). Each unclaimed link
-- moves to the name-only author with the same name (exact spelling first,
-- ignoring case), created when there is none.
--
-- Run after add_paper_author_claims.sql and after backfilling claims with
-- `sync_hf_author_profiles --days 10000`; otherwise claimed papers move too.
--
-- Run as the schema owner (postgres). Idempotent — safe to re-run.

BEGIN;

SET LOCAL search_path = public;

CREATE TEMP TABLE hf_author_namesakes ON COMMIT DROP AS
SELECT a.id AS author_id, a.name, NULL::BIGINT AS namesake_id
FROM authors a
WHERE (a.hf_id IS NOT NULL OR a.hf_username IS NOT NULL)
  AND EXISTS (
      SELECT 1 FROM paper_authors pa
      WHERE pa.author_id = a.id AND NOT pa.claimed
  );

CREATE OR REPLACE TEMP VIEW name_only_authors AS
SELECT id, name FROM authors WHERE hf_id IS NULL AND hf_username IS NULL;

UPDATE hf_author_namesakes h
SET namesake_id = (
    SELECT n.id FROM name_only_authors n
    WHERE lower(n.name) = lower(h.name)
    ORDER BY n.name <> h.name, n.id
    LIMIT 1
);

INSERT INTO authors (name, created_at, updated_at)
SELECT DISTINCT ON (lower(name)) name, now(), now()
FROM hf_author_namesakes
WHERE namesake_id IS NULL
ORDER BY lower(name), name;

UPDATE hf_author_namesakes h
SET namesake_id = (
    SELECT n.id FROM name_only_authors n
    WHERE lower(n.name) = lower(h.name)
    ORDER BY n.name <> h.name, n.id
    LIMIT 1
)
WHERE namesake_id IS NULL;

-- One link per paper and namesake: drop unclaimed links whose namesake is
-- already on the paper, or that another HF-linked namesake also moves there.
DELETE FROM paper_authors pa
USING hf_author_namesakes h
WHERE pa.author_id = h.author_id
  AND NOT pa.claimed
  AND (
      EXISTS (
          SELECT 1 FROM paper_authors x
          WHERE x.paper_id = pa.paper_id AND x.author_id = h.namesake_id
      )
      OR EXISTS (
          SELECT 1 FROM paper_authors x
          JOIN hf_author_namesakes hx ON hx.author_id = x.author_id
          WHERE x.paper_id = pa.paper_id
            AND NOT x.claimed
            AND hx.namesake_id = h.namesake_id
            AND x.author_id < pa.author_id
      )
  );

UPDATE paper_authors pa
SET author_id = h.namesake_id
FROM hf_author_namesakes h
WHERE pa.author_id = h.author_id AND NOT pa.claimed;

SELECT
    count(*) AS hf_authors_split,
    count(DISTINCT namesake_id) AS namesake_authors
FROM hf_author_namesakes;

COMMIT;
