-- Merge authors whose names differ only by letter case ("Tom Aarsen" and
-- "Tom AARSEN") into one author, and index lower(name) for the
-- case-insensitive lookups that importers now use.
--
-- Groups linked to more than one Hugging Face account are left alone: those
-- are different people (or accounts) that happen to share a name.
--
-- The surviving author keeps the Hugging Face-linked row, then the row with
-- the most papers. Its display name becomes the group's best spelling: mixed
-- case before ALL CAPS or all lowercase, then the most-used spelling. Each
-- merged-away ID is recorded in author_aliases so /authors/<old id> resolves.
--
-- Run as the schema owner (postgres). Idempotent — safe to re-run.

BEGIN;

SET LOCAL search_path = public;

CREATE TABLE IF NOT EXISTS author_aliases (
    alias_id BIGINT PRIMARY KEY,
    author_id BIGINT NOT NULL REFERENCES authors(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_author_aliases_author_id
    ON author_aliases (author_id);
CREATE INDEX IF NOT EXISTS idx_authors_lower_name ON authors (lower(name));

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE author_aliases
    TO paperswithcode_user;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
        GRANT SELECT ON TABLE author_aliases TO pwc_staging;
    END IF;
END
$$;

CREATE TEMP TABLE author_case_groups ON COMMIT DROP AS
SELECT
    a.id,
    lower(a.name) AS name_key,
    a.name,
    a.hf_username,
    a.hf_id,
    a.hf_avatar_url,
    a.hf_status,
    a.hf_is_pro,
    (SELECT count(*) FROM paper_authors pa WHERE pa.author_id = a.id) AS paper_count
FROM authors a
WHERE lower(a.name) IN (
    SELECT lower(name)
    FROM authors
    GROUP BY lower(name)
    HAVING count(*) > 1
       AND count(DISTINCT hf_username) <= 1
       AND count(DISTINCT hf_id) <= 1
);

CREATE TEMP TABLE author_case_merge ON COMMIT DROP AS
SELECT DISTINCT ON (name_key)
    name_key,
    id AS keep_id
FROM author_case_groups
ORDER BY name_key, hf_username IS NULL, hf_id IS NULL, paper_count DESC, id;

CREATE TEMP TABLE author_case_display ON COMMIT DROP AS
SELECT DISTINCT ON (name_key)
    name_key,
    name
FROM author_case_groups
ORDER BY
    name_key,
    name = upper(name) OR name = lower(name),
    paper_count DESC,
    id;

CREATE TEMP TABLE author_case_hf ON COMMIT DROP AS
SELECT
    name_key,
    max(hf_username) AS hf_username,
    max(hf_id) AS hf_id,
    max(hf_avatar_url) AS hf_avatar_url,
    max(hf_status) AS hf_status,
    bool_or(coalesce(hf_is_pro, false)) AS hf_is_pro
FROM author_case_groups
GROUP BY name_key;

CREATE TEMP TABLE author_case_aliases ON COMMIT DROP AS
SELECT g.id AS alias_id, m.keep_id AS author_id
FROM author_case_groups g
JOIN author_case_merge m USING (name_key)
WHERE g.id <> m.keep_id;

-- Move paper links; a paper listing both spellings keeps the earlier position.
INSERT INTO paper_authors (paper_id, author_id, author_order)
SELECT pa.paper_id, al.author_id, min(pa.author_order)
FROM paper_authors pa
JOIN author_case_aliases al ON al.alias_id = pa.author_id
GROUP BY pa.paper_id, al.author_id
ON CONFLICT (paper_id, author_id) DO UPDATE
SET author_order = least(paper_authors.author_order, excluded.author_order);

-- Earlier aliases that pointed at a merged-away author follow it.
UPDATE author_aliases aa
SET author_id = al.author_id
FROM author_case_aliases al
WHERE aa.author_id = al.alias_id;

INSERT INTO author_aliases (alias_id, author_id)
SELECT alias_id, author_id FROM author_case_aliases
ON CONFLICT (alias_id) DO UPDATE SET author_id = excluded.author_id;

-- Deleting the duplicates also drops their old paper links (ON DELETE CASCADE)
-- and frees their unique Hugging Face columns for the surviving row.
DELETE FROM authors a
USING author_case_aliases al
WHERE a.id = al.alias_id;

UPDATE authors a
SET
    name = d.name,
    hf_username = coalesce(a.hf_username, h.hf_username),
    hf_id = coalesce(a.hf_id, h.hf_id),
    hf_avatar_url = coalesce(a.hf_avatar_url, h.hf_avatar_url),
    hf_status = coalesce(a.hf_status, h.hf_status),
    hf_is_pro = coalesce(a.hf_is_pro, false) OR h.hf_is_pro,
    updated_at = now()
FROM author_case_merge m
JOIN author_case_display d USING (name_key)
JOIN author_case_hf h USING (name_key)
WHERE a.id = m.keep_id;

COMMIT;
