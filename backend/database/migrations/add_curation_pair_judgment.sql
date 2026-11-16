-- Migration: store the LLM judge's verdicts for Codex/Pi shadow curation pairs
--
-- `pair_judgment` sits on the Pi shadow job next to `pair_diff`. It holds one
-- verdict per disagreement in that diff (graded blind to which runner proposed
-- it), plus the judge model and token usage. Pairs without disagreements get
-- an empty judgment so the gate report can tell them from unjudged pairs.
--
-- Created: 2026-11-16
-- Usage (as postgres, before deploying the backend that maps the column):
--   sudo -u postgres psql -d paperswithcode_hf -X -v ON_ERROR_STOP=1 \
--        < backend/database/migrations/add_curation_pair_judgment.sql
-- Nullable with no default: a metadata-only change.
-- Idempotent: safe to re-run.

BEGIN;

SET LOCAL lock_timeout = '10s';

ALTER TABLE public.paper_curation_jobs
    ADD COLUMN IF NOT EXISTS pair_judgment JSONB;

COMMENT ON COLUMN public.paper_curation_jobs.pair_judgment IS
'Blind LLM-judge verdicts on the disagreements in pair_diff, written by pwc curation judge-pairs.';

DO $$
BEGIN
    IF to_regclass('staging.paper_curation_jobs') IS NOT NULL THEN
        ALTER TABLE staging.paper_curation_jobs
            ADD COLUMN IF NOT EXISTS pair_judgment JSONB;
    END IF;
END $$;

COMMIT;
