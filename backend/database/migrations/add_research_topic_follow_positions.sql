-- Run as the database owner, once, before deploying the code that reads the
-- column. Additive: an account's own order of its followed topics. NULL means
-- never reordered; those rows sort after positioned ones by follow time.
BEGIN;
ALTER TABLE public.research_topic_follows ADD COLUMN IF NOT EXISTS position integer;
DO $$
BEGIN
 IF EXISTS (SELECT 1 FROM information_schema.tables
            WHERE table_schema='staging' AND table_name='research_topic_follows') THEN
   ALTER TABLE staging.research_topic_follows ADD COLUMN IF NOT EXISTS position integer;
 END IF;
END $$;
COMMIT;
