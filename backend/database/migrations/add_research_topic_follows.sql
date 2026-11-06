-- Run as the database owner, once, before deploying the code that reads the
-- table. Additive: an account may follow several free-text topics. Copies each
-- subscription's single topic_id/topic_set_at for accounts that follow no topic
-- in the new table yet, so a re-run never restores a topic replaced there. The
-- old columns stay until the release that stops reading them is live; after the
-- deploy, reconcile by hand any topic_set_at newer than this migration's run.
BEGIN;
CREATE TABLE IF NOT EXISTS public.research_topic_follows (
 hf_subject varchar(255) NOT NULL,
 topic_id bigint NOT NULL REFERENCES public.research_topics(id),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(hf_subject, topic_id)
);
CREATE INDEX IF NOT EXISTS research_topic_follows_topic
 ON public.research_topic_follows(topic_id);
ALTER TABLE public.research_topic_follows OWNER TO paperswithcode_user;
INSERT INTO public.research_topic_follows(hf_subject, topic_id, created_at)
 SELECT hf_subject, topic_id, COALESCE(topic_set_at, clock_timestamp())
 FROM public.research_subscriptions s WHERE topic_id IS NOT NULL
 AND NOT EXISTS (SELECT 1 FROM public.research_topic_follows f WHERE f.hf_subject = s.hf_subject)
 ON CONFLICT DO NOTHING;
DO $$
BEGIN
 IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='staging') THEN
   CREATE TABLE IF NOT EXISTS staging.research_topic_follows
    (LIKE public.research_topic_follows INCLUDING ALL);
   ALTER TABLE staging.research_topic_follows OWNER TO pwc_staging_owner;
   GRANT SELECT,INSERT,UPDATE,DELETE ON staging.research_topic_follows TO pwc_staging;
   REVOKE ALL ON public.research_topic_follows FROM pwc_staging;
   INSERT INTO staging.research_topic_follows(hf_subject, topic_id, created_at)
    SELECT hf_subject, topic_id, COALESCE(topic_set_at, clock_timestamp())
    FROM staging.research_subscriptions s WHERE topic_id IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM staging.research_topic_follows f WHERE f.hf_subject = s.hf_subject)
    ON CONFLICT DO NOTHING;
 END IF;
END $$;
COMMIT;
