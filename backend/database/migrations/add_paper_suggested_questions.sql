-- Migration: suggested questions on paper pages
--
-- Caches the three starter questions gpt-5.6-luna writes from a paper's title
-- and abstract. Rows are created lazily the first time a paper page asks for
-- them, so staging needs INSERT on the shared catalog table too.
--
-- Run as the schema owner (postgres).

CREATE TABLE IF NOT EXISTS public.paper_suggested_questions (
    paper_id BIGINT PRIMARY KEY REFERENCES public.papers(id) ON DELETE CASCADE,
    questions JSONB NOT NULL,
    model VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

GRANT SELECT, INSERT ON TABLE public.paper_suggested_questions
    TO paperswithcode_user;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
        GRANT SELECT, INSERT ON TABLE public.paper_suggested_questions
            TO pwc_staging;
    END IF;
END
$$;

COMMENT ON TABLE public.paper_suggested_questions IS
'Three LLM-generated starter questions per paper, opened in chat from the paper page.';
