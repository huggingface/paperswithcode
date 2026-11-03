-- Migration: let Pi shadow curation jobs be inserted
--
-- Pi shadow jobs use trigger 'pi-shadow', which the trigger check rejected,
-- and they copy paper, kind and policy version from the running Codex stage
-- they mirror, which the one-active-scheduled-stage index rejected. This adds
-- the trigger and leaves Pi shadow rows out of that index, as it already
-- leaves out admin rows.
--
-- Only the public schema: staging keeps its own, older trigger list and never
-- samples Pi shadow pairs.
--
-- Created: 2026-11-03
-- Usage (as postgres):
--   sudo -u postgres psql -d paperswithcode_hf -X -v ON_ERROR_STOP=1 \
--        < backend/database/migrations/allow_pi_shadow_curation_trigger.sql
-- Idempotent: safe to re-run.

BEGIN;

SET LOCAL lock_timeout = '10s';

ALTER TABLE public.paper_curation_jobs
    DROP CONSTRAINT IF EXISTS paper_curation_jobs_trigger_check;
ALTER TABLE public.paper_curation_jobs
    ADD CONSTRAINT paper_curation_jobs_trigger_check
    CHECK (trigger IN (
        'admin', 'hf-daily-cron', 'hf-trending-cron', 'benchmark-promotion',
        'benchmark-gap-cron', 'model-release-radar', 'pi-shadow'
    ));

DROP INDEX IF EXISTS public.uq_active_scheduled_paper_curation_stage;
CREATE UNIQUE INDEX uq_active_scheduled_paper_curation_stage
    ON public.paper_curation_jobs (paper_id, kind, policy_version)
    WHERE trigger NOT IN ('admin', 'pi-shadow')
        AND status IN ('queued', 'dispatching', 'running');

COMMIT;
