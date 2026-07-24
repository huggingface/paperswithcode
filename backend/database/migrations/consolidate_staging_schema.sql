-- Additive staging-isolation migration. Create the pwc_staging LOGIN role and
-- set its password separately before running this file.
\set ON_ERROR_STOP on

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging_owner') THEN
        CREATE ROLE pwc_staging_owner NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
        RAISE EXCEPTION 'create the pwc_staging LOGIN role before this migration';
    END IF;
END $$;

CREATE SCHEMA IF NOT EXISTS staging AUTHORIZATION pwc_staging_owner;
ALTER SCHEMA staging OWNER TO pwc_staging_owner;
GRANT USAGE ON SCHEMA public, staging TO pwc_staging;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO pwc_staging;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO pwc_staging;

DO $$
DECLARE
    table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'chat_messages',
        'chat_sdk_session_summaries',
        'chat_sdk_transcript_entries',
        'chat_sessions'
    ]
    LOOP
        IF to_regclass('public.' || table_name) IS NOT NULL
           AND to_regclass('staging.' || table_name) IS NULL THEN
            EXECUTE format('ALTER TABLE public.%I SET SCHEMA staging', table_name);
        END IF;
    END LOOP;
END $$;

CREATE TABLE IF NOT EXISTS staging.user_bookmarks
    (LIKE public.user_bookmarks INCLUDING ALL);
CREATE TABLE IF NOT EXISTS staging.user_preferences
    (LIKE public.user_preferences INCLUDING ALL);
CREATE TABLE IF NOT EXISTS staging.pending_paper_edits
    (LIKE public.pending_paper_edits INCLUDING ALL);
CREATE TABLE IF NOT EXISTS staging.paper_curation_jobs
    (LIKE public.paper_curation_jobs INCLUDING ALL);

ALTER TABLE staging.user_bookmarks OWNER TO pwc_staging_owner;
ALTER TABLE staging.user_preferences OWNER TO pwc_staging_owner;
ALTER TABLE staging.pending_paper_edits OWNER TO pwc_staging_owner;
ALTER TABLE staging.paper_curation_jobs OWNER TO pwc_staging_owner;

DO $$
DECLARE
    table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'chat_messages',
        'chat_sdk_session_summaries',
        'chat_sdk_transcript_entries',
        'chat_sessions'
    ]
    LOOP
        IF to_regclass('staging.' || table_name) IS NOT NULL THEN
            EXECUTE format('ALTER TABLE staging.%I OWNER TO pwc_staging_owner', table_name);
        END IF;
    END LOOP;
END $$;

REVOKE ALL ON ALL TABLES IN SCHEMA staging FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA staging FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA staging TO pwc_staging;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA staging TO pwc_staging;
ALTER DEFAULT PRIVILEGES FOR ROLE pwc_staging_owner IN SCHEMA staging
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO pwc_staging;
ALTER DEFAULT PRIVILEGES FOR ROLE pwc_staging_owner IN SCHEMA staging
    GRANT USAGE, SELECT ON SEQUENCES TO pwc_staging;

REVOKE ALL ON public.user_bookmarks, public.user_preferences,
    public.pending_paper_edits, public.paper_curation_jobs FROM pwc_staging;
ALTER ROLE pwc_staging SET search_path = staging, public;
ALTER ROLE pwc_staging RESET default_transaction_read_only;
ALTER ROLE pwc_staging SET statement_timeout = '30s';
ALTER ROLE pwc_staging CONNECTION LIMIT 10;

COMMIT;

-- Content-free verification.
SELECT n.nspname AS schema_name, c.relname AS table_name, c.reltuples::bigint
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'staging'
  AND c.relname IN (
      'chat_sessions', 'chat_messages', 'chat_sdk_transcript_entries',
      'chat_sdk_session_summaries', 'user_bookmarks', 'user_preferences',
      'pending_paper_edits', 'paper_curation_jobs'
  )
ORDER BY c.relname;
