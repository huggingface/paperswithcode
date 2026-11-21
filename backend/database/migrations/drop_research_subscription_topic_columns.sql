-- Migration: drop the legacy single-topic columns on research_subscriptions
--
-- `add_research_topic_follows.sql` copied `research_subscriptions.topic_id` /
-- `topic_set_at` into `research_topic_follows`; no release maps the old
-- columns any more. This drops them from `public` and, when present, `staging`.
--
-- Run as the schema owner (postgres) only AFTER the release that ships this
-- file is live in production and the post-deploy `topic_set_at`
-- reconciliation described for `add_research_topic_follows.sql` is done.
-- Refuses to run while any account's legacy topic is unfollowed and was set
-- after that account's newest follow (or the account follows nothing): that
-- topic was written by an old release and never copied. Reconcile such rows by
-- adding the follow or clearing `topic_id`, then re-run. Idempotent: safe to
-- re-run.

BEGIN;

DO $$
DECLARE
    schema_name text;
    unreconciled bigint;
BEGIN
    FOREACH schema_name IN ARRAY ARRAY['public', 'staging'] LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = schema_name
              AND table_name = 'research_subscriptions'
              AND column_name = 'topic_id'
        ) THEN
            EXECUTE format(
                'SELECT count(*) FROM %1$I.research_subscriptions s'
                ' WHERE s.topic_id IS NOT NULL'
                ' AND NOT EXISTS (SELECT 1 FROM %1$I.research_topic_follows f'
                '   WHERE f.hf_subject = s.hf_subject AND f.topic_id = s.topic_id)'
                ' AND (s.topic_set_at IS NULL OR s.topic_set_at > COALESCE('
                '   (SELECT max(f.created_at) FROM %1$I.research_topic_follows f'
                '    WHERE f.hf_subject = s.hf_subject), ''-infinity''::timestamptz))',
                schema_name
            ) INTO unreconciled;
            IF unreconciled > 0 THEN
                RAISE EXCEPTION
                    '%.research_subscriptions has % unreconciled legacy topic(s)',
                    schema_name, unreconciled;
            END IF;
            EXECUTE format(
                'ALTER TABLE %I.research_subscriptions'
                ' DROP COLUMN IF EXISTS topic_id,'
                ' DROP COLUMN IF EXISTS topic_set_at',
                schema_name
            );
        END IF;
    END LOOP;
END
$$;

COMMIT;
