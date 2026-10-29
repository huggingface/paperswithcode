-- Run as the database owner. Additive: a short LLM label for long topics, and
-- embedding matches that fill the feed until Jev finishes the topic's backfill.
BEGIN;
ALTER TABLE public.research_topics ADD COLUMN IF NOT EXISTS label varchar(80);
CREATE TABLE IF NOT EXISTS public.research_topic_previews (
 topic_id bigint NOT NULL REFERENCES public.research_topics(id) ON DELETE CASCADE,
 paper_id bigint NOT NULL REFERENCES public.papers(id) ON DELETE CASCADE,
 PRIMARY KEY(topic_id, paper_id)
);
CREATE INDEX IF NOT EXISTS research_topic_previews_paper
 ON public.research_topic_previews(paper_id);
ALTER TABLE public.research_topic_previews OWNER TO paperswithcode_user;
DO $$
BEGIN
 IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='staging') THEN
   ALTER TABLE staging.research_topics ADD COLUMN IF NOT EXISTS label varchar(80);
   CREATE TABLE IF NOT EXISTS staging.research_topic_previews
    (LIKE public.research_topic_previews INCLUDING ALL);
   ALTER TABLE staging.research_topic_previews OWNER TO pwc_staging_owner;
   GRANT SELECT,INSERT,UPDATE,DELETE ON staging.research_topic_previews TO pwc_staging;
   REVOKE ALL ON public.research_topic_previews FROM pwc_staging;
 END IF;
END $$;
COMMIT;
