-- Move papers that an HF-linked author never claimed to a name-only author.
--
-- Importers used to match arXiv author names to the row of whoever first
-- claimed that name on Hugging Face, so /authors/<id> of a common name listed
-- every namesake's papers. An author linked to an HF account now holds only
-- the papers its account claimed (paper_authors.claimed). Each unclaimed link
-- moves to the name-only author with the same name (exact spelling first,
-- ignoring case), created when there is none.
--
-- An HF-linked author without a single claimed paper got its account from an
-- unconfirmed HF guess (mostly extracted_pending): it keeps its papers and
-- loses the account link instead, which the sync job restores on a real claim.
--
-- Run after add_paper_author_claims.sql and after backfilling claims with
-- `sync_hf_author_profiles --days 10000`; otherwise claimed papers move too.
--
-- Not applied in production. Most of an HF author's genuine papers are
-- unclaimed (HF has no claim for papers it never indexed, nor for many it
-- did), so this also moves real papers off the author, splitting one person
-- across two pages (Yann LeCun would lose about 40 of 102). Author pages list
-- every linked paper, so fix namesake links per author instead of running it.
--
-- Run as the schema owner (postgres). Idempotent — safe to re-run.

BEGIN;

SET LOCAL search_path = public;

UPDATE authors a
SET hf_username = NULL,
    hf_id = NULL,
    hf_avatar_url = NULL,
    hf_status = NULL,
    hf_is_pro = false,
    updated_at = now()
WHERE (a.hf_id IS NOT NULL OR a.hf_username IS NOT NULL)
  AND EXISTS (SELECT 1 FROM paper_authors pa WHERE pa.author_id = a.id)
  AND NOT EXISTS (
      SELECT 1 FROM paper_authors pa WHERE pa.author_id = a.id AND pa.claimed
  );

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

INSERT INTO authors (name, hf_is_pro, created_at, updated_at)
SELECT DISTINCT ON (lower(name)) name, false, now(), now()
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

CREATE TEMP TABLE hf_author_moves ON COMMIT DROP AS
SELECT
    pa.paper_id,
    pa.author_id,
    h.namesake_id,
    row_number() OVER (
        PARTITION BY pa.paper_id, h.namesake_id ORDER BY pa.author_id
    ) AS rank
FROM paper_authors pa
JOIN hf_author_namesakes h ON h.author_id = pa.author_id
WHERE NOT pa.claimed;

ALTER TABLE hf_author_moves ADD PRIMARY KEY (paper_id, author_id);
ANALYZE hf_author_moves;

-- One link per paper and namesake: drop links whose namesake is already on
-- the paper, or that another HF-linked author of that name moves there too.
DELETE FROM paper_authors pa
USING hf_author_moves m
WHERE pa.paper_id = m.paper_id
  AND pa.author_id = m.author_id
  AND (
      m.rank > 1
      OR EXISTS (
          SELECT 1 FROM paper_authors x
          WHERE x.paper_id = m.paper_id AND x.author_id = m.namesake_id
      )
  );

UPDATE paper_authors pa
SET author_id = m.namesake_id
FROM hf_author_moves m
WHERE pa.paper_id = m.paper_id AND pa.author_id = m.author_id;

SELECT
    count(*) AS hf_authors_split,
    count(DISTINCT namesake_id) AS namesake_authors
FROM hf_author_namesakes;

COMMIT;
