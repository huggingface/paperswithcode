-- Run as the database owner. Additive: free-text research topics, Jev verdicts,
-- and one topic per subscription. Staging gets its own copies; only production
-- CRON judges topics, so staging topics stay pending.
BEGIN;
CREATE TABLE IF NOT EXISTS public.research_topics (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 text varchar(300) NOT NULL, normalized varchar(300) NOT NULL UNIQUE,
 backfill_status varchar(20) NOT NULL DEFAULT 'pending',
 backfill_total integer, backfill_done integer NOT NULL DEFAULT 0,
 backfill_attempts integer NOT NULL DEFAULT 0,
 backfill_claimed_at timestamptz, backfill_finished_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK(backfill_status IN ('pending','running','done','failed'))
);
CREATE INDEX IF NOT EXISTS research_topics_pending
 ON public.research_topics(id) WHERE backfill_status IN ('pending','running');
-- One raw Jev score per topic and paper. The feed applies the threshold at read
-- time, so recalibrating never rewrites verdicts. card_sha and policy_version
-- mark a verdict stale when the paper card or the prompt changes.
CREATE TABLE IF NOT EXISTS public.research_topic_verdicts (
 topic_id bigint NOT NULL REFERENCES public.research_topics(id) ON DELETE CASCADE,
 paper_id bigint NOT NULL REFERENCES public.papers(id) ON DELETE CASCADE,
 score real NOT NULL, card_sha char(64) NOT NULL, policy_version varchar(32) NOT NULL,
 judged_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(topic_id, paper_id)
);
CREATE INDEX IF NOT EXISTS research_topic_verdicts_paper
 ON public.research_topic_verdicts(paper_id);
ALTER TABLE public.research_subscriptions
 ADD COLUMN IF NOT EXISTS topic_id bigint REFERENCES public.research_topics(id),
 ADD COLUMN IF NOT EXISTS topic_set_at timestamptz;
CREATE INDEX IF NOT EXISTS research_subscriptions_topic
 ON public.research_subscriptions(topic_id) WHERE topic_id IS NOT NULL;
DO $$
DECLARE t text;
BEGIN
 FOREACH t IN ARRAY ARRAY['research_topics','research_topic_verdicts'] LOOP
   EXECUTE format('ALTER TABLE public.%I OWNER TO paperswithcode_user',t);
   IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='staging') THEN
     EXECUTE format('CREATE TABLE IF NOT EXISTS staging.%I (LIKE public.%I INCLUDING ALL)',t,t);
     EXECUTE format('ALTER TABLE staging.%I OWNER TO pwc_staging_owner',t);
     EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON staging.%I TO pwc_staging',t);
     EXECUTE format('REVOKE ALL ON public.%I FROM pwc_staging',t);
   END IF;
 END LOOP;
 IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='staging') THEN
   ALTER TABLE staging.research_subscriptions
    ADD COLUMN IF NOT EXISTS topic_id bigint, ADD COLUMN IF NOT EXISTS topic_set_at timestamptz;
 END IF;
END $$;
COMMIT;
