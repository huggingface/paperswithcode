-- Run as the database owner. Additive: a one-sentence LLM summary shown on each
-- topic page, filled by the per-minute topic CRON.
BEGIN;
ALTER TABLE public.research_topics ADD COLUMN IF NOT EXISTS summary varchar(300);
DO $$
BEGIN
 IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='staging') THEN
   ALTER TABLE staging.research_topics ADD COLUMN IF NOT EXISTS summary varchar(300);
 END IF;
END $$;
COMMIT;
