-- Migration: daily benchmark-gap review and creation jobs
--
-- Lets the `enqueue_benchmark_gap_review` CRON review agent-reported benchmark
-- gaps (`benchmark_curation_candidates`), record each decision, and run one
-- scoped `add-benchmark` curation job per approved candidate.
--
-- Run as the schema owner (postgres) before deploying the release that reads
-- these columns. Updates `public` and, when present, the `staging` copies. The
-- staging job table predates `candidate_id` and names its trigger check
-- differently, so staging gets the columns, kind check, foreign key, and
-- unique-active indexes but keeps its own trigger and scope checks.
-- Idempotent: safe to re-run.

BEGIN;

ALTER TABLE public.benchmark_curation_candidates
    ADD COLUMN IF NOT EXISTS review_reason TEXT,
    ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS reviewed_paper_count INTEGER,
    ADD COLUMN IF NOT EXISTS deferred_until TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS merged_into_id UUID
        REFERENCES public.benchmark_curation_candidates(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS resolution JSONB;

ALTER TABLE public.benchmark_curation_candidates
    DROP CONSTRAINT IF EXISTS benchmark_curation_candidates_status_check;
ALTER TABLE public.benchmark_curation_candidates
    ADD CONSTRAINT benchmark_curation_candidates_status_check
    CHECK (status IN ('candidate', 'approved', 'promoted', 'rejected', 'merged'));

CREATE INDEX IF NOT EXISTS idx_benchmark_curation_candidates_review
    ON public.benchmark_curation_candidates (status, distinct_paper_count);

ALTER TABLE public.paper_curation_jobs
    ADD COLUMN IF NOT EXISTS benchmark_candidate_id UUID
        REFERENCES public.benchmark_curation_candidates(id) ON DELETE CASCADE;

ALTER TABLE public.paper_curation_jobs
    DROP CONSTRAINT IF EXISTS paper_curation_jobs_kind_check;
ALTER TABLE public.paper_curation_jobs
    ADD CONSTRAINT paper_curation_jobs_kind_check
    CHECK (kind IN (
        'add-evals', 'enrich-paper', 'resolve-model-paper',
        'review-benchmark-gaps', 'add-benchmark'
    ));

ALTER TABLE public.paper_curation_jobs
    DROP CONSTRAINT IF EXISTS paper_curation_jobs_trigger_check;
ALTER TABLE public.paper_curation_jobs
    ADD CONSTRAINT paper_curation_jobs_trigger_check
    CHECK (trigger IN (
        'admin', 'hf-daily-cron', 'hf-trending-cron', 'benchmark-promotion',
        'benchmark-gap-cron'
    ));

ALTER TABLE public.paper_curation_jobs
    DROP CONSTRAINT IF EXISTS paper_curation_jobs_scope_check;
ALTER TABLE public.paper_curation_jobs
    ADD CONSTRAINT paper_curation_jobs_scope_check
    CHECK (
        (kind = 'resolve-model-paper' AND candidate_id IS NOT NULL
            AND paper_id IS NULL AND benchmark_candidate_id IS NULL)
        OR (kind = 'add-benchmark' AND benchmark_candidate_id IS NOT NULL
            AND paper_id IS NULL AND candidate_id IS NULL)
        OR (kind = 'review-benchmark-gaps' AND paper_id IS NULL
            AND candidate_id IS NULL AND benchmark_candidate_id IS NULL)
        OR (kind IN ('add-evals', 'enrich-paper') AND paper_id IS NOT NULL
            AND candidate_id IS NULL AND benchmark_candidate_id IS NULL)
    );

CREATE INDEX IF NOT EXISTS idx_paper_curation_jobs_benchmark_candidate
    ON public.paper_curation_jobs (benchmark_candidate_id, created_at);

CREATE UNIQUE INDEX IF NOT EXISTS uq_active_benchmark_candidate_job
    ON public.paper_curation_jobs (benchmark_candidate_id)
    WHERE kind = 'add-benchmark' AND status IN ('queued', 'dispatching', 'running');

CREATE UNIQUE INDEX IF NOT EXISTS uq_active_benchmark_gap_review
    ON public.paper_curation_jobs (kind)
    WHERE kind = 'review-benchmark-gaps' AND status IN ('queued', 'dispatching', 'running');

DO $$
BEGIN
    IF to_regclass('staging.benchmark_curation_candidates') IS NOT NULL THEN
        ALTER TABLE staging.benchmark_curation_candidates
            ADD COLUMN IF NOT EXISTS review_reason TEXT,
            ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS reviewed_paper_count INTEGER,
            ADD COLUMN IF NOT EXISTS deferred_until TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS merged_into_id UUID
                REFERENCES staging.benchmark_curation_candidates(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS resolution JSONB;
        ALTER TABLE staging.benchmark_curation_candidates
            DROP CONSTRAINT IF EXISTS benchmark_curation_candidates_status_check;
        ALTER TABLE staging.benchmark_curation_candidates
            ADD CONSTRAINT benchmark_curation_candidates_status_check
            CHECK (status IN ('candidate', 'approved', 'promoted', 'rejected', 'merged'));
        CREATE INDEX IF NOT EXISTS idx_staging_benchmark_curation_candidates_review
            ON staging.benchmark_curation_candidates (status, distinct_paper_count);
    END IF;
    IF to_regclass('staging.paper_curation_jobs') IS NOT NULL THEN
        ALTER TABLE staging.paper_curation_jobs
            ADD COLUMN IF NOT EXISTS benchmark_candidate_id UUID;
        IF to_regclass('staging.benchmark_curation_candidates') IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'paper_curation_jobs_benchmark_candidate_id_fkey'
                  AND conrelid = 'staging.paper_curation_jobs'::regclass
            ) THEN
            ALTER TABLE staging.paper_curation_jobs
                ADD CONSTRAINT paper_curation_jobs_benchmark_candidate_id_fkey
                FOREIGN KEY (benchmark_candidate_id)
                REFERENCES staging.benchmark_curation_candidates(id) ON DELETE CASCADE;
        END IF;
        CREATE INDEX IF NOT EXISTS idx_staging_paper_curation_jobs_benchmark_candidate
            ON staging.paper_curation_jobs (benchmark_candidate_id, created_at);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_staging_active_benchmark_candidate_job
            ON staging.paper_curation_jobs (benchmark_candidate_id)
            WHERE kind = 'add-benchmark'
              AND status IN ('queued', 'dispatching', 'running');
        CREATE UNIQUE INDEX IF NOT EXISTS uq_staging_active_benchmark_gap_review
            ON staging.paper_curation_jobs (kind)
            WHERE kind = 'review-benchmark-gaps'
              AND status IN ('queued', 'dispatching', 'running');
        ALTER TABLE staging.paper_curation_jobs
            DROP CONSTRAINT IF EXISTS paper_curation_jobs_kind_check;
        ALTER TABLE staging.paper_curation_jobs
            ADD CONSTRAINT paper_curation_jobs_kind_check
            CHECK (kind IN (
                'add-evals', 'enrich-paper', 'resolve-model-paper',
                'review-benchmark-gaps', 'add-benchmark'
            ));
    END IF;
END
$$;

COMMIT;
