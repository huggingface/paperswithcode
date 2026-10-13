-- Run as the database owner. Additive; no historical email events are backfilled.
BEGIN;
CREATE TABLE IF NOT EXISTS public.research_follows (
 hf_subject varchar(255) NOT NULL, kind varchar(20) NOT NULL,
 entity_id bigint NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(hf_subject, kind, entity_id),
 CHECK(kind IN ('task','method','benchmark','author','organization'))
);
CREATE TABLE IF NOT EXISTS public.research_subscriptions (
 hf_subject varchar(255) PRIMARY KEY, email varchar(320), enabled boolean NOT NULL DEFAULT false,
 opted_in_at timestamptz, unsubscribe_token varchar(64) NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS public.research_suppressions (
 email varchar(320) PRIMARY KEY, reason varchar(32) NOT NULL
);
CREATE TABLE IF NOT EXISTS public.research_digests (
 hf_subject varchar(255) NOT NULL, window_end timestamptz NOT NULL,
 status varchar(20) NOT NULL DEFAULT 'pending', payload json NOT NULL,
 first_attempt_at timestamptz, provider_id text, PRIMARY KEY(hf_subject, window_end)
);
CREATE TABLE IF NOT EXISTS public.research_events (
 event_key text PRIMARY KEY, paper_key text NOT NULL, paper_id bigint NOT NULL,
 evaluation_id bigint, dataset_id bigint, discovered_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS research_events_discovered ON public.research_events(discovered_at);
CREATE INDEX IF NOT EXISTS research_events_paper ON public.research_events(paper_key);
-- Insertion captures discovery even for raw SQL importers. UPDATE never alerts.
CREATE OR REPLACE FUNCTION public.capture_research_event() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
DECLARE p public.papers; k text; e text;
BEGIN
 IF TG_TABLE_NAME = 'papers' THEN
   p := NEW;
   IF NEW.arxiv_id IS NOT NULL AND EXISTS (
     SELECT 1 FROM public.papers WHERE arxiv_id = NEW.arxiv_id AND id <> NEW.id
   ) THEN RETURN NEW; END IF;
 ELSE
   SELECT * INTO p FROM public.papers WHERE id = NEW.paper_id;
 END IF;
 -- Unknown/future dates and historical imports do not alert. Use the earliest
 -- publication across versions, so a revision cannot rejuvenate an old paper.
 IF p.date_published IS NULL OR p.date_published > CURRENT_DATE
 OR p.date_published < CURRENT_DATE - 30 OR EXISTS (
   SELECT 1 FROM public.papers WHERE arxiv_id = p.arxiv_id AND date_published < CURRENT_DATE - 30
 ) THEN RETURN NEW; END IF;
 k := CASE WHEN p.arxiv_id IS NOT NULL THEN 'arxiv:' || p.arxiv_id ELSE 'paper:' || p.id END;
 IF TG_TABLE_NAME = 'papers' THEN
   INSERT INTO public.research_events(event_key,paper_key,paper_id)
   VALUES ('paper:' || k,k,p.id) ON CONFLICT DO NOTHING;
 ELSE
   -- Stable result identity excludes scores, so replacement/correction imports
   -- cannot resend a previously discovered model/benchmark result.
   e := 'result:' || md5(jsonb_build_array(k,NEW.task_id,NEW.dataset_id,
     coalesce(NEW.model_name,''),coalesce(NEW.harness,''))::text);
   INSERT INTO public.research_events(event_key,paper_key,paper_id,evaluation_id,dataset_id)
   VALUES (e,k,p.id,NEW.id,NEW.dataset_id) ON CONFLICT DO NOTHING;
 END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS research_paper_insert ON public.papers;
CREATE TRIGGER research_paper_insert AFTER INSERT ON public.papers
FOR EACH ROW EXECUTE FUNCTION public.capture_research_event();
DROP TRIGGER IF EXISTS research_result_insert ON public.evaluations;
CREATE TRIGGER research_result_insert AFTER INSERT ON public.evaluations
FOR EACH ROW EXECUTE FUNCTION public.capture_research_event();
-- Seed existing result identities with an old discovery time. A delete/reinsert
-- correction must not turn the launch catalog into an email backlog.
INSERT INTO public.research_events(event_key,paper_key,paper_id,evaluation_id,dataset_id,discovered_at)
SELECT 'result:' || md5(jsonb_build_array(
 CASE WHEN p.arxiv_id IS NOT NULL THEN 'arxiv:' || p.arxiv_id ELSE 'paper:' || p.id END,
 e.task_id,e.dataset_id,coalesce(e.model_name,''),coalesce(e.harness,''))::text),
 CASE WHEN p.arxiv_id IS NOT NULL THEN 'arxiv:' || p.arxiv_id ELSE 'paper:' || p.id END,
 p.id,e.id,e.dataset_id,'1970-01-01'::timestamptz
FROM public.evaluations e JOIN public.papers p ON p.id=e.paper_id
WHERE p.date_published >= CURRENT_DATE - 30
ON CONFLICT DO NOTHING;
DO $$
DECLARE t text;
BEGIN
 FOREACH t IN ARRAY ARRAY['research_follows','research_subscriptions','research_suppressions','research_digests'] LOOP
   EXECUTE format('ALTER TABLE public.%I OWNER TO paperswithcode_user',t);
   IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='staging') THEN
     EXECUTE format('CREATE TABLE IF NOT EXISTS staging.%I (LIKE public.%I INCLUDING ALL)',t,t);
     EXECUTE format('ALTER TABLE staging.%I OWNER TO pwc_staging_owner',t);
     EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON staging.%I TO pwc_staging',t);
     EXECUTE format('REVOKE ALL ON public.%I FROM pwc_staging',t);
   END IF;
 END LOOP;
END $$;
ALTER TABLE public.research_events OWNER TO paperswithcode_user;
GRANT SELECT ON public.research_events TO pwc_staging;
COMMIT;
