-- Run as the database owner, once, before deploying the code that reads the
-- columns. Additive: free-text topics get a creator, a creator-controlled
-- public flag and an admin hide timestamp; accounts get a switch for showing
-- their avatar on topics they follow.
--
-- Topics and accounts that exist when the columns are first added were set up
-- under a private-only promise, so they start private / hidden. Only rows
-- created afterwards take the public defaults. The creator is the earliest
-- remaining follower; topics nobody follows stay without one.
BEGIN;
DO $$
DECLARE
 schema_name text;
BEGIN
 FOREACH schema_name IN ARRAY ARRAY['public', 'staging'] LOOP
   CONTINUE WHEN NOT EXISTS (
     SELECT 1 FROM information_schema.tables
     WHERE table_schema = schema_name AND table_name = 'research_topics');
   IF NOT EXISTS (
     SELECT 1 FROM information_schema.columns
     WHERE table_schema = schema_name AND table_name = 'research_topics'
     AND column_name = 'is_public') THEN
     EXECUTE format('ALTER TABLE %I.research_topics
       ADD COLUMN created_by_hf_subject varchar(255),
       ADD COLUMN is_public boolean NOT NULL DEFAULT false,
       ADD COLUMN hidden_at timestamptz', schema_name);
     EXECUTE format('ALTER TABLE %I.research_topics
       ALTER COLUMN is_public SET DEFAULT true', schema_name);
     EXECUTE format('UPDATE %I.research_topics t SET created_by_hf_subject = (
       SELECT f.hf_subject FROM %I.research_topic_follows f
       WHERE f.topic_id = t.id ORDER BY f.created_at, f.hf_subject LIMIT 1)',
       schema_name, schema_name);
   END IF;
   IF NOT EXISTS (
     SELECT 1 FROM information_schema.columns
     WHERE table_schema = schema_name AND table_name = 'research_subscriptions'
     AND column_name = 'show_as_follower') THEN
     EXECUTE format('ALTER TABLE %I.research_subscriptions
       ADD COLUMN show_as_follower boolean NOT NULL DEFAULT false', schema_name);
     EXECUTE format('ALTER TABLE %I.research_subscriptions
       ALTER COLUMN show_as_follower SET DEFAULT true', schema_name);
   END IF;
 END LOOP;
END $$;
COMMIT;
