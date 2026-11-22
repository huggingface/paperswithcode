-- Migration: record the agent session stored with a curation trace
--
-- Curation runners now upload the agent's native session file (a Codex
-- rollout or a Pi session) as `session.jsonl` beside the trace manifest, so
-- the Hugging Face trace viewer can render it. `trace_session_sha256` holds
-- that object's content hash and is null for jobs whose trace has no session,
-- which lets the admin UI link the viewer only when the file exists.
--
-- Created: 2026-11-22
-- Usage (as postgres, before deploying the backend that maps the column):
--   sudo -u postgres psql -d paperswithcode_hf -X -v ON_ERROR_STOP=1 \
--        < backend/database/migrations/add_curation_trace_session.sql
-- Nullable with no default: a metadata-only change.
-- Idempotent: safe to re-run.

BEGIN;

SET LOCAL lock_timeout = '10s';

ALTER TABLE public.paper_curation_jobs
    ADD COLUMN IF NOT EXISTS trace_session_sha256 VARCHAR(64);

COMMENT ON COLUMN public.paper_curation_jobs.trace_session_sha256 IS
'SHA-256 of the session.jsonl agent session stored beside the trace manifest; null when none was stored.';

DO $$
BEGIN
    IF to_regclass('staging.paper_curation_jobs') IS NOT NULL THEN
        ALTER TABLE staging.paper_curation_jobs
            ADD COLUMN IF NOT EXISTS trace_session_sha256 VARCHAR(64);
    END IF;
END
$$;

COMMIT;
