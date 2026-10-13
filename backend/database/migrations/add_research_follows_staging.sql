-- Staging preview only: no production tables, catalog triggers, or CRON changes.
BEGIN;
CREATE TABLE IF NOT EXISTS staging.research_follows (
 hf_subject varchar(255) NOT NULL, kind varchar(20) NOT NULL,
 entity_id bigint NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(hf_subject,kind,entity_id),
 CHECK(kind IN ('task','method','benchmark','author','organization'))
);
CREATE TABLE IF NOT EXISTS staging.research_subscriptions (
 hf_subject varchar(255) PRIMARY KEY, email varchar(320), enabled boolean NOT NULL DEFAULT false,
 opted_in_at timestamptz, unsubscribe_token varchar(64) NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS staging.research_suppressions (
 email varchar(320) PRIMARY KEY, reason varchar(32) NOT NULL
);
CREATE TABLE IF NOT EXISTS staging.research_digests (
 hf_subject varchar(255) NOT NULL, window_end timestamptz NOT NULL,
 status varchar(20) NOT NULL DEFAULT 'pending', payload json NOT NULL,
 first_attempt_at timestamptz, provider_id text, PRIMARY KEY(hf_subject,window_end)
);
DO $$
DECLARE t text;
BEGIN
 FOREACH t IN ARRAY ARRAY['research_follows','research_subscriptions','research_suppressions','research_digests'] LOOP
   EXECUTE format('ALTER TABLE staging.%I OWNER TO pwc_staging_owner',t);
   EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON staging.%I TO pwc_staging',t);
 END LOOP;
END $$;
COMMIT;
