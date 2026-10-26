-- Abstract entity linking: per-entity linking mode and curated aliases on the
-- catalog, plus the judged mentions of each paper abstract.
-- Run as the schema owner (postgres). Idempotent.

-- How literal matches of an entity are handled: link every match ('always'),
-- let the judge model decide per abstract ('judge'), or never link ('never').
ALTER TABLE public.methods
    ADD COLUMN IF NOT EXISTS abstract_linking VARCHAR(8) NOT NULL DEFAULT 'judge',
    ADD COLUMN IF NOT EXISTS aliases TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE public.datasets
    ADD COLUMN IF NOT EXISTS abstract_linking VARCHAR(8) NOT NULL DEFAULT 'judge',
    ADD COLUMN IF NOT EXISTS aliases TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE public.frameworks
    ADD COLUMN IF NOT EXISTS abstract_linking VARCHAR(8) NOT NULL DEFAULT 'judge',
    ADD COLUMN IF NOT EXISTS aliases TEXT[] NOT NULL DEFAULT '{}';

DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['methods', 'datasets', 'frameworks'] LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = tbl || '_abstract_linking_check'
        ) THEN
            EXECUTE format(
                'ALTER TABLE public.%I ADD CONSTRAINT %I CHECK '
                '(abstract_linking IN (''always'', ''judge'', ''never''))',
                tbl, tbl || '_abstract_linking_check'
            );
        END IF;
    END LOOP;
END $$;

-- One row per (paper, entity, occurrence). Rejected candidates are kept with
-- linked = false so they are not judged again for the same abstract.
CREATE TABLE IF NOT EXISTS public.paper_abstract_mentions (
    paper_id BIGINT NOT NULL REFERENCES public.papers(id) ON DELETE CASCADE,
    entity_type VARCHAR(16) NOT NULL,
    entity_id BIGINT NOT NULL,
    start_offset INTEGER NOT NULL,
    end_offset INTEGER NOT NULL,
    surface TEXT NOT NULL,
    abstract_sha CHAR(64) NOT NULL,
    linked BOOLEAN NOT NULL,
    judge VARCHAR(64),
    score REAL,
    prompt_version VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (paper_id, entity_type, entity_id, start_offset),
    CONSTRAINT paper_abstract_mentions_entity_type_check
        CHECK (entity_type IN ('method', 'dataset', 'framework')),
    CONSTRAINT paper_abstract_mentions_span_check
        CHECK (start_offset >= 0 AND end_offset > start_offset)
);

CREATE INDEX IF NOT EXISTS idx_paper_abstract_mentions_entity
    ON public.paper_abstract_mentions(entity_type, entity_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.paper_abstract_mentions
    TO paperswithcode_user;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
        GRANT SELECT ON TABLE public.paper_abstract_mentions TO pwc_staging;
    END IF;
END $$;

COMMENT ON TABLE public.paper_abstract_mentions IS
    'Literal catalog mentions in paper abstracts and whether each is linked; '
    'served only while abstract_sha matches the current abstract.';
