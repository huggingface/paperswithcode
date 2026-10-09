BEGIN;
SET LOCAL lock_timeout = '5s';
ALTER TABLE public.papers ADD COLUMN IF NOT EXISTS hf_daily_featured_on DATE;
CREATE INDEX IF NOT EXISTS ix_papers_hf_daily_featured_on
    ON public.papers (hf_daily_featured_on);
COMMIT;
